import uuid
import logging
from datetime import datetime
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.reminder import Reminder, ReminderStatus
from app.models.user import User
from app.core.scheduler import scheduler
from app.bot.notifier import send_telegram_message
from app.db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)

async def trigger_reminder_notification(reminder_id: uuid.UUID):
    """
    Job function to be executed by APScheduler.
    """
    logger.info(f"Executing reminder job for {reminder_id}")
    async with AsyncSessionLocal() as session:
        # Fetch reminder with user
        # We need to construct a new query
        stmt = select(Reminder, User).join(User).where(Reminder.id == reminder_id)
        result = await session.execute(stmt)
        record = result.first()
        
        if not record:
            logger.warning(f"Reminder {reminder_id} not found during job execution.")
            return

        reminder, user = record
        
        if reminder.status != ReminderStatus.PENDING:
            logger.info(f"Reminder {reminder_id} is {reminder.status}, skipping notification.")
            return

        # Send notification
        message = f"🔔 *Напоминание*\n{reminder.title}"
        if reminder.description:
            message += f"\n\n{reminder.description}"
        
        # Add basic info to help debugging
        logger.info(f"Sending reminder to {user.telegram_id}")
            
        await send_telegram_message(user.telegram_id, message)
        
        # Update status
        reminder.status = ReminderStatus.COMPLETED
        await session.commit()

class ReminderService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_reminder(
        self, 
        user_id: uuid.UUID, 
        title: str, 
        due_at: datetime, 
        description: str = None, 
        contact_id: uuid.UUID = None
    ) -> Reminder:
        """
        Create a new reminder and schedule it.
        """
        reminder = Reminder(
            user_id=user_id,
            title=title,
            due_at=due_at,
            description=description,
            contact_id=contact_id,
            status=ReminderStatus.PENDING
        )
        self.session.add(reminder)
        await self.session.commit()
        await self.session.refresh(reminder)
        
        # Schedule job in APScheduler
        try:
            scheduler.add_job(
                trigger_reminder_notification,
                'date',
                run_date=due_at,
                args=[reminder.id],
                id=str(reminder.id),
                replace_existing=True
            )
            logger.info(f"Scheduled reminder {reminder.id} for {due_at}")
        except Exception as e:
            logger.error(f"Failed to schedule reminder job: {e}")
            # Consider rolling back or ignoring? For MVP, just log.
        
        return reminder

    async def get_user_reminders(
        self, 
        user_id: uuid.UUID, 
        status: Optional[ReminderStatus] = None, 
        limit: int = 10, 
        offset: int = 0
    ) -> List[Reminder]:
        stmt = select(Reminder).where(Reminder.user_id == user_id)
        if status:
            stmt = stmt.where(Reminder.status == status)
        stmt = stmt.order_by(Reminder.due_at.asc()).limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return result.scalars().all()
    
    async def delete_reminder(self, reminder_id: uuid.UUID) -> bool:
        reminder = await self.session.get(Reminder, reminder_id)
        if reminder:
            try:
                scheduler.remove_job(str(reminder.id))
            except Exception:
                pass # Job might already be gone
            await self.session.delete(reminder)
            await self.session.commit()
            return True
        return False

    async def complete_reminder(self, reminder_id: uuid.UUID) -> bool:
        reminder = await self.session.get(Reminder, reminder_id)
        if reminder:
            reminder.status = ReminderStatus.COMPLETED
            try:
                # Try to remove pending job if exists (e.g. if completed early)
                scheduler.remove_job(str(reminder.id))
            except Exception:
                pass
            await self.session.commit()
            return True
        return False
