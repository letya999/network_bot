from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from app.models.contact import Contact, ContactStatus
from app.models.interaction import Interaction, InteractionType
from typing import Dict, Any, List
from app.services.reminder_service import ReminderService
from app.core.config import settings
from app.config.constants import (
    UNKNOWN_CONTACT_NAME,
    MAX_SEARCH_QUERY_LENGTH
)
from datetime import datetime, timedelta
import dateparser
import uuid
import logging

logger = logging.getLogger(__name__)

class ContactService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_contact(self, user_id: uuid.UUID, data: Dict[str, Any]) -> Contact:
        contact = Contact(
            user_id=user_id,
            name=data.get("name", UNKNOWN_CONTACT_NAME),
            company=data.get("company"),
            role=data.get("role"),
            phone=data.get("phone"),
            telegram_username=data.get("telegram_username"),
            email=data.get("email"),
            linkedin_url=data.get("linkedin_url"),
            event_name=data.get("event"),
            what_looking_for=data.get("what_looking_for"),
            can_help_with=data.get("can_help_with"),
            topics=data.get("topics"),
            agreements=data.get("agreements"),
            follow_up_action=data.get("follow_up_action"),
            raw_transcript=data.get("raw_transcript"),
            status=ContactStatus.ACTIVE.value,
            osint_data={},
            attributes=data  # Store full dynamic data found by prompt
        )
        self.session.add(contact)
        await self.session.flush()
        
        # Create interaction (initial meeting)
        notes = data.get("notes")
        if not notes and data.get("raw_transcript"):
            notes = "Transcribed from voice"
            
        interaction = Interaction(
            contact_id=contact.id,
            type=InteractionType.MET.value,
            notes=notes
        )
        self.session.add(interaction)
        await self.session.commit()
        await self.session.refresh(contact)
        
        # Process Reminders if extracted
        if data.get("reminders"):
            reminder_service = ReminderService(self.session)
            for reminder_data in data["reminders"]:
                try:
                    due_date_str = reminder_data.get("due_date")
                    title = reminder_data.get("title")
                    if due_date_str and title:
                        # Try parsing date using dateparser
                        due_date = dateparser.parse(due_date_str, settings={'PREFER_DATES_FROM': 'future'})

                        # Default to tomorrow if parsing fails or returns past
                        if not due_date or due_date < datetime.now():
                             due_date = datetime.now() + timedelta(days=1)

                        await reminder_service.create_reminder(
                            user_id=user_id,
                            contact_id=contact.id,
                            title=title,
                            due_at=due_date,
                            description=reminder_data.get("description")
                        )
                except Exception:
                    logger.exception("Failed to create extracted reminder")

        # Schedule auto-enrichment if enabled and contact has a name
        if settings.AUTO_ENRICH_ON_CREATE and contact.name and contact.name != UNKNOWN_CONTACT_NAME:
            try:
                from app.core.scheduler import scheduler, auto_enrich_contact_job
                # Schedule enrichment 5 seconds after creation
                run_date = datetime.now() + timedelta(seconds=5)
                scheduler.add_job(
                    auto_enrich_contact_job,
                    'date',
                    run_date=run_date,
                    args=[contact.id],
                    id=f"enrich_{contact.id}",
                    replace_existing=True
                )
                logger.info(f"Scheduled auto-enrichment for contact {contact.id}")
            except Exception:
                logger.exception("Failed to schedule auto-enrichment")

        return contact

    async def get_recent_contacts(self, user_id: uuid.UUID, limit: int = 10, offset: int = 0) -> List[Contact]:
        query = select(Contact).where(Contact.user_id == user_id).order_by(Contact.created_at.desc()).limit(limit).offset(offset)
        result = await self.session.execute(query)
        return result.scalars().all()

    async def find_contacts(self, user_id: uuid.UUID, query_str: str) -> List[Contact]:
        # Input validation: limit query length and sanitize
        if not query_str or len(query_str) > MAX_SEARCH_QUERY_LENGTH:
            return []

        # Sanitize query to prevent SQL injection (escape special chars)
        sanitized_query = query_str.replace("%", "\\%").replace("_", "\\_")

        # Use parameterized queries with proper escaping
        search_pattern = f"%{sanitized_query}%"
        stmt = select(Contact).where(
            Contact.user_id == user_id,
            or_(
                Contact.name.ilike(search_pattern),
                Contact.company.ilike(search_pattern)
            )
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def update_contact(self, contact_id: uuid.UUID, data: Dict[str, Any]) -> Contact:
        result = await self.session.execute(select(Contact).where(Contact.id == contact_id))
        contact = result.scalar_one_or_none()
        if not contact:
            return None
        
        # Smart merge: only update if new value is meaningful
        for field, value in data.items():
            if not hasattr(contact, field):
                continue
                
            # Skip None values - don't overwrite existing data with None
            if value is None:
                continue
            
            # For string fields, skip empty strings - don't overwrite existing data
            if isinstance(value, str) and not value.strip():
                continue
            
            # Special case: don't overwrite a real name with "Неизвестно"
            if field == 'name' and value == UNKNOWN_CONTACT_NAME:
                current_name = getattr(contact, field)
                if current_name and current_name != UNKNOWN_CONTACT_NAME:
                    continue
            
            # Update the field
            setattr(contact, field, value)
        
        # Update attributes (merge, don't replace)
        if contact.attributes is None:
            contact.attributes = {}
        current_attrs = dict(contact.attributes) if contact.attributes else {}
        current_attrs.update(data)
        contact.attributes = current_attrs
        
        await self.session.commit()
        await self.session.refresh(contact)
        return contact

    async def get_all_contacts(self, user_id: uuid.UUID) -> List[Contact]:
        query = select(Contact).where(Contact.user_id == user_id).order_by(Contact.created_at.desc())
        result = await self.session.execute(query)
        return result.scalars().all()

    async def find_by_identifiers(self, user_id: uuid.UUID, phone: str = None, telegram: str = None) -> Contact:
        if not phone and not telegram:
            return None
        
        conditions = []
        if phone:
            # Simple normalization for comparison could be added here if needed
            conditions.append(Contact.phone == phone)
        if telegram:
            clean_tg = telegram.lower().lstrip("@")
            conditions.append(Contact.telegram_username == clean_tg)
            
        if not conditions:
            return None

        stmt = select(Contact).where(
            Contact.user_id == user_id,
            or_(*conditions)
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()
