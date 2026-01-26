import logging
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from app.models.contact import Contact
from app.models.user import User
import uuid

logger = logging.getLogger(__name__)


class PulseService:
    """
    Service for detecting relationship pulse opportunities:
    - Triangulation: Finding connections through shared companies
    - Common Ground: Finding shared interests or topics
    """
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def detect_company_triangulation(
        self, 
        user_id: uuid.UUID, 
        new_contact: Contact
    ) -> List[Contact]:
        """
        Detect triangulation opportunities when a new contact is added.
        Returns existing contacts from the same company.
        
        Args:
            user_id: The user's UUID
            new_contact: The newly added contact
            
        Returns:
            List of existing contacts from the same company (excluding the new contact)
        """
        if not new_contact.company:
            return []
        
        # Find other contacts from the same company
        stmt = select(Contact).where(
            and_(
                Contact.user_id == user_id,
                Contact.company.ilike(f"%{new_contact.company}%"),
                Contact.id != new_contact.id,
                Contact.status == "active"
            )
        ).order_by(Contact.created_at.desc())
        
        result = await self.session.execute(stmt)
        existing_contacts = result.scalars().all()
        
        logger.info(
            f"Found {len(existing_contacts)} triangulation opportunities "
            f"for company '{new_contact.company}'"
        )
        
        return list(existing_contacts)
    
    async def detect_topic_overlap(
        self,
        user_id: uuid.UUID,
        contact: Contact,
        min_shared_topics: int = 1
    ) -> List[Contact]:
        """
        Find contacts with overlapping topics/interests.
        
        Args:
            user_id: The user's UUID
            contact: The contact to find overlaps for
            min_shared_topics: Minimum number of shared topics required
            
        Returns:
            List of contacts with shared topics
        """
        if not contact.topics:
            return []
        
        # PostgreSQL array overlap operator
        stmt = select(Contact).where(
            and_(
                Contact.user_id == user_id,
                Contact.id != contact.id,
                Contact.topics.overlap(contact.topics),
                Contact.status == "active"
            )
        ).order_by(Contact.created_at.desc())
        
        result = await self.session.execute(stmt)
        overlapping_contacts = result.scalars().all()
        
        # Filter by minimum shared topics if needed
        if min_shared_topics > 1:
            filtered = []
            for c in overlapping_contacts:
                shared = set(contact.topics) & set(c.topics or [])
                if len(shared) >= min_shared_topics:
                    filtered.append(c)
            return filtered
        
        return list(overlapping_contacts)
    
    def generate_triangulation_message(
        self,
        new_contact: Contact,
        existing_contacts: List[Contact]
    ) -> str:
        """
        Generate a friendly message suggesting reconnection based on triangulation.
        
        Args:
            new_contact: The newly added contact
            existing_contacts: List of existing contacts from same company
            
        Returns:
            Formatted message with suggestions
        """
        if not existing_contacts:
            return ""
        
        message = f"🔗 *Триангуляция обнаружена!*\n\n"
        message += f"Вы добавили *{new_contact.name}* из компании *{new_contact.company}*.\n\n"
        
        if len(existing_contacts) == 1:
            old = existing_contacts[0]
            message += f"У вас уже есть контакт из этой компании:\n"
            message += f"👤 *{old.name}*"
            if old.role:
                message += f" ({old.role})"
            message += "\n\n"
            message += f"💡 *Повод написать:*\n"
            message += f"_\"Привет, {old.name.split()[0]}! Тут познакомился с твоим коллегой "
            message += f"{new_contact.name.split()[0]}, вспомнил про тебя. Как дела?\"_"
        else:
            message += f"У вас уже есть {len(existing_contacts)} контакт(а/ов) из этой компании:\n\n"
            for old in existing_contacts[:3]:  # Show max 3
                message += f"👤 *{old.name}*"
                if old.role:
                    message += f" — {old.role}"
                message += "\n"
            
            if len(existing_contacts) > 3:
                message += f"_...и ещё {len(existing_contacts) - 3}_\n"
            
            message += "\n💡 Это отличный повод для reconnect!"
        
        return message
    
    def generate_topic_overlap_message(
        self,
        contact: Contact,
        overlapping_contacts: List[Contact]
    ) -> str:
        """
        Generate a message about contacts with shared interests.
        
        Args:
            contact: The contact to analyze
            overlapping_contacts: Contacts with shared topics
            
        Returns:
            Formatted message
        """
        if not overlapping_contacts:
            return ""
        
        message = f"⭐ *Общие интересы найдены!*\n\n"
        message += f"*{contact.name}* интересуется: {', '.join(contact.topics or [])}\n\n"
        message += f"Похожие интересы у:\n"
        
        for c in overlapping_contacts[:3]:
            shared = set(contact.topics) & set(c.topics or [])
            message += f"👤 *{c.name}* — {', '.join(shared)}\n"
        
        if len(overlapping_contacts) > 3:
            message += f"_...и ещё {len(overlapping_contacts) - 3}_\n"
        
        message += "\n💡 Возможно, стоит их познакомить?"
        
        return message
