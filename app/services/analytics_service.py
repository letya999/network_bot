from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, and_, or_
from app.models.contact import Contact
from app.models.interaction import Interaction, InteractionType
from typing import Dict, Any, List, Optional
import uuid
from datetime import datetime, timedelta

class AnalyticsService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_networking_stats(self, user_id: uuid.UUID, days: int = 30) -> Dict[str, Any]:
        """
        Get networking statistics for a user for the last N days.
        """
        since_date = datetime.now() - timedelta(days=days)

        # 1. Total new contacts
        contacts_stmt = select(func.count(Contact.id)).where(
            Contact.user_id == user_id,
            Contact.created_at >= since_date
        )
        total_contacts = (await self.session.execute(contacts_stmt)).scalar() or 0

        # 2. Contacts by event
        event_stmt = select(Contact.event_name, func.count(Contact.id)).where(
            Contact.user_id == user_id,
            Contact.created_at >= since_date
        ).group_by(Contact.event_name).order_by(desc(func.count(Contact.id)))
        events_res = await self.session.execute(event_stmt)
        by_event = {row[0] or "Unknown": row[1] for row in events_res.all()}

        # 3. Funnel stats (interactions)
        # Contacts created in this period
        # Follow-ups sent (MESSAGE_SENT) for these contacts
        # Responses received (MESSAGE_RECEIVED) for these contacts
        # Meetings held (MEETING) for these contacts
        
        # We need to find interactions for contacts created in the period OR interactions created in the period.
        # Let's count interactions created in the period.
        
        interaction_stmt = select(Interaction.type, func.count(Interaction.id)).join(Contact).where(
            Contact.user_id == user_id,
            Interaction.date >= since_date
        ).group_by(Interaction.type)
        interaction_res = await self.session.execute(interaction_stmt)
        by_interaction = {row[0]: row[1] for row in interaction_res.all()}

        # 4. Roles distribution (simplified, based on role field)
        role_stmt = select(Contact.role, func.count(Contact.id)).where(
            Contact.user_id == user_id,
            Contact.created_at >= since_date
        ).group_by(Contact.role).order_by(desc(func.count(Contact.id))).limit(5)
        role_res = await self.session.execute(role_stmt)
        by_role = {row[0] or "Other": row[1] for row in role_res.all()}

        return {
            "period_days": days,
            "total_new_contacts": total_contacts,
            "by_event": by_event,
            "funnel": {
                "contacts": total_contacts,
                "follow_ups": by_interaction.get(InteractionType.MESSAGE_SENT.value, 0),
                "responses": by_interaction.get(InteractionType.MESSAGE_RECEIVED.value, 0),
                "meetings": by_interaction.get(InteractionType.MEETING.value, 0)
            },
            "by_role": by_role
        }

    async def get_inactive_contacts(self, user_id: uuid.UUID, days: int = 30) -> List[Contact]:
        """
        Find contacts with no interactions in the last N days.
        """
        since_date = datetime.now() - timedelta(days=days)
        
        # Contacts where the latest interaction date is older than since_date
        # Or no interactions at all (though 'met' is created on create)
        
        # Subquery for latest interaction per contact
        latest_interaction = select(
            Interaction.contact_id, 
            func.max(Interaction.date).label("max_date")
        ).group_by(Interaction.contact_id).subquery()
        
        stmt = select(Contact).outerjoin(
            latest_interaction, Contact.id == latest_interaction.c.contact_id
        ).where(
            Contact.user_id == user_id,
            and_(
                Contact.status == "active",
                or_(
                    latest_interaction.c.max_date < since_date,
                    latest_interaction.c.max_date == None
                )
            )
        ).order_by(Contact.created_at.desc())
        
        result = await self.session.execute(stmt)
        return result.scalars().all()
