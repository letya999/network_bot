import logging
import secrets
import uuid
from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from app.models.contact import Contact
from app.models.contact_share import ContactShare, ShareVisibility, ContactPurchase
from app.models.payment import Payment

logger = logging.getLogger(__name__)

# Default visible fields for shared contacts
DEFAULT_VISIBLE_FIELDS = [
    "name", "company", "role", "what_looking_for", "can_help_with", "topics"
]

# All possible shareable fields
ALL_SHAREABLE_FIELDS = [
    "name", "company", "role", "phone", "email", "telegram_username",
    "linkedin_url", "event_name", "what_looking_for", "can_help_with",
    "topics", "agreements", "follow_up_action"
]

CONTACT_FIELDS = {
    "phone": "Телефон",
    "email": "Email",
    "telegram_username": "Telegram",
    "linkedin_url": "LinkedIn",
}

PROFILE_FIELDS = {
    "name": "Имя",
    "company": "Компания",
    "role": "Роль",
    "what_looking_for": "Ищет",
    "can_help_with": "Может помочь",
    "topics": "Темы",
    "event_name": "Событие",
    "agreements": "Договоренности",
    "follow_up_action": "След. шаг",
}


class SharingService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def share_contact(
        self,
        owner_id: uuid.UUID,
        contact_id: uuid.UUID,
        visibility: str = ShareVisibility.PUBLIC.value,
        visible_fields: list = None,
        hidden_fields: list = None,
        price_amount: str = "0",
        price_currency: str = "RUB",
        description: str = None,
        allowed_user_ids: list = None,
    ) -> ContactShare:
        # Check if already shared
        existing = await self.session.execute(
            select(ContactShare).where(
                ContactShare.contact_id == contact_id,
                ContactShare.owner_id == owner_id,
                ContactShare.is_active == True,
            )
        )
        share = existing.scalars().first()

        if share:
            # Update existing share
            share.visibility = visibility
            share.visible_fields = visible_fields or DEFAULT_VISIBLE_FIELDS
            share.hidden_fields = hidden_fields or []
            share.price_amount = price_amount
            share.price_currency = price_currency
            share.description = description
            share.allowed_user_ids = allowed_user_ids or []
        else:
            share = ContactShare(
                contact_id=contact_id,
                owner_id=owner_id,
                visibility=visibility,
                visible_fields=visible_fields or DEFAULT_VISIBLE_FIELDS,
                hidden_fields=hidden_fields or [],
                price_amount=price_amount,
                price_currency=price_currency,
                description=description,
                share_token=secrets.token_urlsafe(32),
                allowed_user_ids=allowed_user_ids or [],
            )
            self.session.add(share)

        await self.session.commit()
        await self.session.refresh(share)
        return share

    async def unshare_contact(self, share_id: uuid.UUID) -> bool:
        result = await self.session.execute(
            select(ContactShare).where(ContactShare.id == share_id)
        )
        share = result.scalars().first()
        if share:
            share.is_active = False
            await self.session.commit()
            return True
        return False

    async def get_share_by_token(self, token: str) -> Optional[ContactShare]:
        result = await self.session.execute(
            select(ContactShare).where(
                ContactShare.share_token == token,
                ContactShare.is_active == True,
            )
        )
        return result.scalars().first()

    async def get_share_by_id(self, share_id: uuid.UUID) -> Optional[ContactShare]:
        result = await self.session.execute(
            select(ContactShare).where(ContactShare.id == share_id)
        )
        return result.scalars().first()

    async def get_user_shares(self, owner_id: uuid.UUID, active_only: bool = True) -> List[ContactShare]:
        stmt = select(ContactShare).where(ContactShare.owner_id == owner_id)
        if active_only:
            stmt = stmt.where(ContactShare.is_active == True)
        stmt = stmt.order_by(ContactShare.created_at.desc())
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_public_shares(self, limit: int = 20, offset: int = 0) -> List[ContactShare]:
        stmt = (
            select(ContactShare)
            .where(
                ContactShare.is_active == True,
                ContactShare.visibility.in_([
                    ShareVisibility.PUBLIC.value,
                    ShareVisibility.PAID.value,
                ])
            )
            .order_by(ContactShare.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def can_user_view(self, share: ContactShare, viewer_user_id: uuid.UUID) -> bool:
        """Check if a user can view this shared contact."""
        if share.owner_id == viewer_user_id:
            return True
        if share.visibility == ShareVisibility.PUBLIC.value:
            return True
        if share.visibility == ShareVisibility.PRIVATE.value:
            return viewer_user_id in (share.allowed_user_ids or [])
        if share.visibility == ShareVisibility.PAID.value:
            # Check if they purchased it
            purchased = await self.has_purchased(share.id, viewer_user_id)
            return purchased
        return False

    async def has_purchased(self, share_id: uuid.UUID, buyer_id: uuid.UUID) -> bool:
        result = await self.session.execute(
            select(ContactPurchase).where(
                ContactPurchase.share_id == share_id,
                ContactPurchase.buyer_id == buyer_id,
            )
        )
        return result.scalars().first() is not None

    async def get_filtered_contact_data(self, share: ContactShare, contact: Contact) -> Dict[str, Any]:
        """Return contact data filtered by share visibility settings."""
        data = {}
        visible = share.visible_fields or ALL_SHAREABLE_FIELDS
        hidden = share.hidden_fields or []

        for field in ALL_SHAREABLE_FIELDS:
            if field in visible and field not in hidden:
                value = getattr(contact, field, None)
                if value is not None:
                    data[field] = value

        return data

    async def purchase_contact(
        self,
        share_id: uuid.UUID,
        buyer_id: uuid.UUID,
        payment_id: uuid.UUID = None,
        amount_paid: str = "0",
        currency: str = "RUB",
    ) -> ContactPurchase:
        """Record a purchase and copy the contact to buyer's list."""
        share = await self.get_share_by_id(share_id)
        if not share:
            raise ValueError("Share not found")

        # Get original contact
        result = await self.session.execute(
            select(Contact).where(Contact.id == share.contact_id)
        )
        original = result.scalars().first()
        if not original:
            raise ValueError("Original contact not found")

        # Create a copy in buyer's account
        visible = share.visible_fields or ALL_SHAREABLE_FIELDS
        hidden = share.hidden_fields or []

        copy_data = {}
        for field in ALL_SHAREABLE_FIELDS:
            if field in visible and field not in hidden:
                value = getattr(original, field, None)
                if value is not None:
                    copy_data[field] = value

        # Ensure name exists
        if "name" not in copy_data:
            copy_data["name"] = original.name or "Без имени"

        copied = Contact(
            user_id=buyer_id,
            name=copy_data.get("name", "Без имени"),
            company=copy_data.get("company"),
            role=copy_data.get("role"),
            phone=copy_data.get("phone"),
            email=copy_data.get("email"),
            telegram_username=copy_data.get("telegram_username"),
            linkedin_url=copy_data.get("linkedin_url"),
            event_name=copy_data.get("event_name"),
            what_looking_for=copy_data.get("what_looking_for"),
            can_help_with=copy_data.get("can_help_with"),
            topics=copy_data.get("topics"),
            agreements=copy_data.get("agreements"),
            follow_up_action=copy_data.get("follow_up_action"),
            status="active",
            attributes={
                "purchased_from_share": str(share_id),
                "purchased_from_user": str(share.owner_id),
                "source": "marketplace",
            },
        )
        self.session.add(copied)
        await self.session.flush()

        # Create purchase record
        purchase = ContactPurchase(
            share_id=share_id,
            buyer_id=buyer_id,
            seller_id=share.owner_id,
            copied_contact_id=copied.id,
            payment_id=payment_id,
            amount_paid=amount_paid,
            currency=currency,
        )
        self.session.add(purchase)

        # Update stats
        current_count = int(share.purchase_count or "0")
        share.purchase_count = str(current_count + 1)

        await self.session.commit()
        await self.session.refresh(purchase)
        return purchase

    async def get_user_purchases(self, buyer_id: uuid.UUID) -> List[ContactPurchase]:
        stmt = (
            select(ContactPurchase)
            .where(ContactPurchase.buyer_id == buyer_id)
            .order_by(ContactPurchase.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def update_field_visibility(
        self, share_id: uuid.UUID, visible_fields: list, hidden_fields: list = None
    ) -> Optional[ContactShare]:
        result = await self.session.execute(
            select(ContactShare).where(ContactShare.id == share_id)
        )
        share = result.scalars().first()
        if not share:
            return None
        share.visible_fields = visible_fields
        share.hidden_fields = hidden_fields or []
        await self.session.commit()
        await self.session.refresh(share)
        return share
