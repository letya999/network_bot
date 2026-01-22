from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from app.models.contact import Contact, ContactStatus
from app.models.interaction import Interaction, InteractionType
from typing import Dict, Any, List
import uuid

class ContactService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_contact(self, user_id: uuid.UUID, data: Dict[str, Any]) -> Contact:
        contact = Contact(
            user_id=user_id,
            name=data.get("name", "Неизвестно"),
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
        return contact

    async def get_recent_contacts(self, user_id: uuid.UUID, limit: int = 10, offset: int = 0) -> List[Contact]:
        query = select(Contact).where(Contact.user_id == user_id).order_by(Contact.created_at.desc()).limit(limit).offset(offset)
        result = await self.session.execute(query)
        return result.scalars().all()

    async def find_contacts(self, user_id: uuid.UUID, query_str: str) -> List[Contact]:
        # Input validation: limit query length and sanitize
        if not query_str or len(query_str) > 100:
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
        
        for k, v in data.items():
            if v is not None and hasattr(contact, k):
                # Avoid overwriting with "Unknown" if we already have a name?
                # Let handler decide.
                setattr(contact, k, v)
        
        # update attributes if something new is there
        if contact.attributes is None:
            contact.attributes = {}
        # We merge top level keys?
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
