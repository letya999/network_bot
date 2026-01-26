import time
import logging
import uuid
from typing import Dict, Any, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.contact_service import ContactService
from app.models.contact import Contact
from app.config.constants import CONTACT_MERGE_TIMEOUT_SECONDS, UNKNOWN_CONTACT_NAME

logger = logging.getLogger(__name__)

class ContactMergeService:
    """
    Service responsible for merging newly extracted contact data with existing contacts
    based on temporal proximity or identifying information.
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self.contact_service = ContactService(session)

    async def process_contact_data(
        self, 
        user_id: uuid.UUID, 
        data: Dict[str, Any], 
        user_data: Dict[str, Any]
    ) -> Tuple[Contact, bool]:
        """
        Determines whether to create a new contact or update/merge with a recent one.
        
        Args:
            user_id: Internal database User UUID
            data: Newly extracted contact data from Gemini/Regex
            user_data: Telegram context user_data for tracking recent interactions
            
        Returns:
            Tuple of (Contact, was_merged)
        """
        now = time.time()
        
        # 1. Check for temporal merge target (from context)
        # We check both last_voice_id and last_contact_id for cross-modality merging
        last_voice_id = user_data.get("last_voice_id")
        last_voice_time = user_data.get("last_voice_time", 0)
        
        last_contact_id = user_data.get("last_contact_id")
        last_contact_time = user_data.get("last_contact_time", 0)
        
        active_id = None
        
        # Priority 1: Check most recent interaction regardless of type
        if last_voice_id and (now - last_voice_time < CONTACT_MERGE_TIMEOUT_SECONDS):
            active_id = last_voice_id
        elif last_contact_id and (now - last_contact_time < CONTACT_MERGE_TIMEOUT_SECONDS):
            active_id = last_contact_id
            
        # 2. Check for duplicate by identifier if we haven't found a context target
        # This prevents creating two "Ivan Ivanov" if they have the same phone/telegram
        phone = data.get("phone")
        telegram = data.get("telegram_username")
        
        existing_by_id = await self.contact_service.find_by_identifiers(user_id, phone, telegram)
        
        # 3. Decision Logic
        if active_id:
            # Merging with context contact
            contact = await self.contact_service.update_contact(active_id, data)
            logger.info(f"Merged contact data into active context contact {active_id}")
            return contact, True
            
        if existing_by_id:
            # Merging with existing contact found by phone/TG
            contact = await self.contact_service.update_contact(existing_by_id.id, data)
            logger.info(f"Merged contact data into existing contact {existing_by_id.id} by identifier")
            return contact, True
            
        # 4. Fallback: Create new contact
        contact = await self.contact_service.create_contact(user_id, data)
        logger.info(f"Created new contact because no merge target was found")
        return contact, False

    def is_reminder_only(self, data: Dict[str, Any]) -> bool:
        """
        Checks if the data contains only reminders without enough identity info.
        """
        name = data.get("name", "").lower()
        has_identity = name not in [UNKNOWN_CONTACT_NAME.lower(), "unknown"] and name.strip() != ""
        has_company = bool(data.get("company"))
        has_reminders = bool(data.get("reminders"))
        
        return not has_identity and not has_company and has_reminders
