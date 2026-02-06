"""Webapp API endpoints for the React frontend (Telegram Mini App + Website)."""
import logging
import hashlib
import hmac
import json
from urllib.parse import parse_qs
from typing import Optional
from fastapi import APIRouter, HTTPException, Header, Depends, Query
from pydantic import BaseModel, field_validator
from sqlalchemy import select, func
from app.db.session import AsyncSessionLocal
from app.models import User, Contact, ContactShare, ContactPurchase, Subscription, Payment
from app.models.contact_share import ShareVisibility
from app.models.subscription import SubscriptionStatus
from app.models.payment import PaymentStatus, PaymentType, PaymentProvider
from app.services.user_service import UserService
from app.services.contact_service import ContactService
from app.services.sharing_service import SharingService, ALL_SHAREABLE_FIELDS, DEFAULT_VISIBLE_FIELDS
from app.services.subscription_service import SubscriptionService
from app.services.payment_service import PaymentService, YooKassaService
from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/webapp", tags=["webapp"])

VALID_VISIBILITIES = {v.value for v in ShareVisibility}
VALID_PROVIDERS = {"free", "yookassa", "telegram"}


# ========================
# Auth helpers
# ========================

def _parse_telegram_init_data(init_data: str) -> Optional[dict]:
    """Validate and parse Telegram WebApp initData."""
    if not init_data:
        return None

    bot_token = settings.TELEGRAM_BOT_TOKEN
    if not bot_token:
        return None

    try:
        parsed = parse_qs(init_data)
        data_check_string_parts = []
        received_hash = None

        for key in sorted(parsed.keys()):
            if key == 'hash':
                received_hash = parsed[key][0]
            else:
                data_check_string_parts.append(f"{key}={parsed[key][0]}")

        if not received_hash:
            return None

        data_check_string = '\n'.join(data_check_string_parts)

        secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
        computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

        if not hmac.compare_digest(computed_hash, received_hash):
            logger.warning("Telegram initData hash mismatch")
            return None

        user_json = parsed.get('user', [None])[0]
        if user_json:
            return json.loads(user_json)
        return None

    except Exception:
        logger.exception("Error parsing Telegram initData")
        return None


async def get_current_user(
    x_telegram_init_data: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
) -> Optional[User]:
    """Extract current user from Telegram initData or Bearer token."""
    telegram_user = None

    if x_telegram_init_data:
        telegram_user = _parse_telegram_init_data(x_telegram_init_data)

    if telegram_user:
        async with AsyncSessionLocal() as session:
            user_service = UserService(session)
            user = await user_service.get_or_create_user(
                telegram_id=telegram_user['id'],
                username=telegram_user.get('username'),
                first_name=telegram_user.get('first_name'),
                last_name=telegram_user.get('last_name'),
            )
            return user

    return None


def require_user(user: Optional[User] = Depends(get_current_user)):
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


def _is_admin(user: User) -> bool:
    admin_ids = settings.ADMIN_TELEGRAM_IDS.split(",")
    return str(user.telegram_id) in [a.strip() for a in admin_ids if a.strip()]


# ========================
# Request/Response models
# ========================

class CreateShareRequest(BaseModel):
    contact_id: str
    visibility: str = "public"
    visible_fields: list = DEFAULT_VISIBLE_FIELDS
    hidden_fields: list = []
    price_amount: float = 0
    price_currency: str = "RUB"
    description: str = ""

    @field_validator("visibility")
    @classmethod
    def validate_visibility(cls, v):
        if v not in VALID_VISIBILITIES:
            raise ValueError(f"Invalid visibility: {v}")
        return v

    @field_validator("price_amount")
    @classmethod
    def validate_price(cls, v):
        if v < 0:
            raise ValueError("Price cannot be negative")
        if v > 1_000_000:
            raise ValueError("Price too high")
        return v

    @field_validator("description")
    @classmethod
    def validate_description(cls, v):
        return (v or "")[:500]


class UpdateShareRequest(BaseModel):
    visibility: Optional[str] = None
    visible_fields: Optional[list] = None
    hidden_fields: Optional[list] = None
    price_amount: Optional[float] = None
    price_currency: Optional[str] = None
    description: Optional[str] = None

    @field_validator("visibility")
    @classmethod
    def validate_visibility(cls, v):
        if v is not None and v not in VALID_VISIBILITIES:
            raise ValueError(f"Invalid visibility: {v}")
        return v

    @field_validator("price_amount")
    @classmethod
    def validate_price(cls, v):
        if v is not None and (v < 0 or v > 1_000_000):
            raise ValueError("Invalid price")
        return v


class PurchaseRequest(BaseModel):
    share_id: str
    provider: str = "free"

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, v):
        if v not in VALID_PROVIDERS:
            raise ValueError(f"Invalid provider: {v}")
        return v


class SubscriptionPayRequest(BaseModel):
    provider: str = "yookassa"

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, v):
        if v not in {"yookassa", "telegram"}:
            raise ValueError(f"Invalid provider: {v}")
        return v


# ========================
# Catalog (public)
# ========================

@router.get("/catalog")
async def get_catalog(
    limit: int = Query(20, ge=1, le=50),
    offset: int = Query(0, ge=0),
):
    """Get public shared contacts."""
    async with AsyncSessionLocal() as session:
        sharing_service = SharingService(session)
        # Uses selectinload(ContactShare.contact) - no N+1
        shares = await sharing_service.get_public_shares(limit=limit, offset=offset)

        result = []
        for s in shares:
            contact = s.contact
            if not contact:
                continue
            result.append({
                "id": str(s.id),
                "contact_name": contact.name,
                "contact_company": contact.company,
                "contact_role": contact.role,
                "visibility": s.visibility,
                "price_amount": float(s.price_amount or 0),
                "price_currency": s.price_currency,
                "description": s.description,
                "view_count": s.view_count,
                "purchase_count": s.purchase_count,
            })

    return {"shares": result}


@router.get("/share/{token}")
async def get_share_by_token(token: str, user: Optional[User] = Depends(get_current_user)):
    """Get a shared contact by its token."""
    async with AsyncSessionLocal() as session:
        sharing_service = SharingService(session)
        share = await sharing_service.get_share_by_token(token)
        if not share or not share.is_active:
            raise HTTPException(status_code=404, detail="Share not found")
        return await _build_share_response(session, share, user)


@router.get("/share/id/{share_id}")
async def get_share_by_id(share_id: str, user: Optional[User] = Depends(get_current_user)):
    """Get a shared contact by ID."""
    async with AsyncSessionLocal() as session:
        sharing_service = SharingService(session)
        share = await sharing_service.get_share_by_id(share_id)
        if not share or not share.is_active:
            raise HTTPException(status_code=404, detail="Share not found")
        return await _build_share_response(session, share, user)


async def _build_share_response(session, share, user):
    """Build response for a shared contact."""
    sharing_service = SharingService(session)
    contact_service = ContactService(session)
    contact = await contact_service.get_contact_by_id(share.contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    is_owner = user and share.owner_id == user.id
    already_purchased = user and await sharing_service.has_purchased(share.id, user.id) if user else False

    can_see_details = is_owner or already_purchased or share.visibility == ShareVisibility.PUBLIC.value

    if can_see_details:
        contact_data = await sharing_service.get_filtered_contact_data(share, contact)
    else:
        contact_data = {}
        for f in ["name", "company", "role", "what_looking_for"]:
            if f in (share.visible_fields or []):
                val = getattr(contact, f, None)
                if val:
                    contact_data[f] = val

    # Atomic view count increment
    await sharing_service.increment_view_count(share.id)

    return {
        "id": str(share.id),
        "contact_id": str(share.contact_id),
        "visibility": share.visibility,
        "price_amount": float(share.price_amount or 0),
        "price_currency": share.price_currency,
        "description": share.description,
        "visible_fields": share.visible_fields,
        "view_count": share.view_count + 1,
        "purchase_count": share.purchase_count,
        "is_owner": is_owner,
        "already_purchased": already_purchased,
        "contact_data": contact_data,
    }


# ========================
# User's shares
# ========================

@router.get("/my/shares")
async def get_my_shares(user: User = Depends(require_user)):
    async with AsyncSessionLocal() as session:
        sharing_service = SharingService(session)
        # Uses selectinload(ContactShare.contact) - no N+1
        shares = await sharing_service.get_user_shares(user.id)

        result = []
        for s in shares:
            contact = s.contact
            result.append({
                "id": str(s.id),
                "contact_id": str(s.contact_id),
                "contact_name": contact.name if contact else "?",
                "visibility": s.visibility,
                "price_amount": float(s.price_amount or 0),
                "price_currency": s.price_currency,
                "visible_fields": s.visible_fields,
                "view_count": s.view_count,
                "purchase_count": s.purchase_count,
                "share_token": s.share_token,
            })

    return {"shares": result}


@router.post("/my/shares")
async def create_share(req: CreateShareRequest, user: User = Depends(require_user)):
    async with AsyncSessionLocal() as session:
        sub_service = SubscriptionService(session)
        if not await sub_service.has_seller_access(user.id):
            raise HTTPException(status_code=403, detail="Seller subscription required")

        sharing_service = SharingService(session)
        share = await sharing_service.share_contact(
            owner_id=user.id,
            contact_id=req.contact_id,
            visibility=req.visibility,
            visible_fields=req.visible_fields,
            hidden_fields=req.hidden_fields,
            price_amount=req.price_amount,
            price_currency=req.price_currency,
            description=req.description,
        )

    return {"id": str(share.id), "share_token": share.share_token}


@router.patch("/my/shares/{share_id}")
async def update_share(share_id: str, req: UpdateShareRequest, user: User = Depends(require_user)):
    async with AsyncSessionLocal() as session:
        sharing_service = SharingService(session)
        share = await sharing_service.get_share_by_id(share_id)
        if not share or share.owner_id != user.id:
            raise HTTPException(status_code=404, detail="Share not found")

        updates = req.model_dump(exclude_none=True)
        if "visible_fields" in updates:
            await sharing_service.update_field_visibility(
                share.id, updates["visible_fields"], updates.get("hidden_fields", [])
            )
        if "visibility" in updates:
            share.visibility = updates["visibility"]
        if "price_amount" in updates:
            from decimal import Decimal
            share.price_amount = Decimal(str(updates["price_amount"]))
        if "price_currency" in updates:
            share.price_currency = updates["price_currency"]
        if "description" in updates:
            share.description = (updates["description"] or "")[:500]
        await session.commit()

    return {"status": "ok"}


@router.delete("/my/shares/{share_id}")
async def delete_share(share_id: str, user: User = Depends(require_user)):
    async with AsyncSessionLocal() as session:
        sharing_service = SharingService(session)
        share = await sharing_service.get_share_by_id(share_id)
        if not share or share.owner_id != user.id:
            raise HTTPException(status_code=404, detail="Share not found")
        await sharing_service.unshare_contact(share.id)
    return {"status": "ok"}


# ========================
# Contacts
# ========================

@router.get("/my/contacts")
async def get_my_contacts(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(require_user),
):
    async with AsyncSessionLocal() as session:
        contact_service = ContactService(session)
        contacts = await contact_service.get_recent_contacts(user.id, limit=limit, offset=offset)
        result = [
            {
                "id": str(c.id),
                "name": c.name,
                "company": c.company,
                "role": c.role,
                "status": c.status,
            }
            for c in contacts
        ]
    return {"contacts": result}


@router.get("/my/contacts/{contact_id}")
async def get_my_contact(contact_id: str, user: User = Depends(require_user)):
    async with AsyncSessionLocal() as session:
        contact_service = ContactService(session)
        contact = await contact_service.get_contact_by_id(contact_id)
        if not contact or contact.user_id != user.id:
            raise HTTPException(status_code=404, detail="Contact not found")

        return {
            "id": str(contact.id),
            "name": contact.name,
            "company": contact.company,
            "role": contact.role,
            "phone": contact.phone,
            "email": contact.email,
            "telegram_username": contact.telegram_username,
            "linkedin_url": contact.linkedin_url,
            "what_looking_for": contact.what_looking_for,
            "can_help_with": contact.can_help_with,
            "topics": contact.topics,
            "event_name": contact.event_name,
            "status": contact.status,
        }


# ========================
# Purchases
# ========================

@router.get("/my/purchases")
async def get_my_purchases(user: User = Depends(require_user)):
    async with AsyncSessionLocal() as session:
        sharing_service = SharingService(session)
        # Uses selectinload for copied_contact and seller - no N+1
        purchases = await sharing_service.get_user_purchases(user.id)

        result = []
        for p in purchases:
            contact_name = "?"
            if p.copied_contact:
                contact_name = p.copied_contact.name or "?"

            seller_name = p.seller.name if p.seller else None

            result.append({
                "id": str(p.id),
                "share_id": str(p.share_id),
                "contact_name": contact_name,
                "seller_name": seller_name,
                "copied_contact_id": str(p.copied_contact_id) if p.copied_contact_id else None,
                "amount_paid": float(p.amount_paid or 0),
                "currency": p.currency,
                "created_at": p.created_at.isoformat() if p.created_at else None,
            })

    return {"purchases": result}


@router.post("/purchase")
async def purchase_contact(req: PurchaseRequest, user: User = Depends(require_user)):
    async with AsyncSessionLocal() as session:
        sharing_service = SharingService(session)
        share = await sharing_service.get_share_by_id(req.share_id)
        if not share or not share.is_active:
            raise HTTPException(status_code=404, detail="Share not found")

        if share.owner_id == user.id:
            raise HTTPException(status_code=400, detail="Cannot purchase your own contact")

        if await sharing_service.has_purchased(share.id, user.id):
            raise HTTPException(status_code=400, detail="Already purchased")

        price = float(share.price_amount or 0)

        if req.provider == "free" or price == 0:
            purchase = await sharing_service.purchase_contact(
                share_id=share.id,
                buyer_id=user.id,
                amount_paid=0,
                currency="RUB",
            )
            return {"status": "ok", "purchase_id": str(purchase.id)}

        elif req.provider == "yookassa":
            yookassa = YooKassaService()
            if not yookassa.is_configured:
                raise HTTPException(status_code=400, detail="YooKassa not configured")

            payment_service = PaymentService(session)
            payment = await payment_service.create_payment(
                user_id=user.id,
                payment_type=PaymentType.CONTACT_PURCHASE.value,
                provider=PaymentProvider.YOOKASSA.value,
                amount=price,
                currency="RUB",
                contact_share_id=share.id,
            )

            yookassa_payment = await yookassa.create_payment(
                amount=price,
                currency="RUB",
                description="Покупка контакта - NetworkBot",
                metadata={
                    "payment_id": str(payment.id),
                    "user_id": str(user.id),
                    "share_id": str(share.id),
                    "type": "contact_purchase",
                },
            )

            confirmation_url = yookassa_payment.get("confirmation", {}).get("confirmation_url", "")
            provider_id = yookassa_payment.get("id", "")

            await payment_service.update_payment_status(
                payment.id,
                PaymentStatus.PENDING.value,
                provider_payment_id=provider_id,
            )

            return {"status": "pending", "confirmation_url": confirmation_url}

        else:
            raise HTTPException(status_code=400, detail="Unknown provider")


# ========================
# Subscription
# ========================

@router.get("/my/subscription")
async def get_subscription(user: User = Depends(require_user)):
    async with AsyncSessionLocal() as session:
        sub_service = SubscriptionService(session)
        sub = await sub_service.get_active_subscription(user.id)

        if not sub:
            return {"status": "none", "plan": None}

        return {
            "status": sub.status,
            "plan": sub.plan,
            "provider": sub.provider,
            "price_amount": float(sub.price_amount or 0),
            "price_currency": sub.price_currency,
            "period_end": sub.current_period_end.isoformat() if sub.current_period_end else None,
        }


@router.post("/subscription/pay")
async def create_subscription_payment(req: SubscriptionPayRequest, user: User = Depends(require_user)):
    if req.provider == "yookassa":
        yookassa = YooKassaService()
        if not yookassa.is_configured:
            raise HTTPException(status_code=400, detail="YooKassa not configured")

        async with AsyncSessionLocal() as session:
            payment_service = PaymentService(session)
            payment = await payment_service.create_payment(
                user_id=user.id,
                payment_type=PaymentType.SUBSCRIPTION.value,
                provider=PaymentProvider.YOOKASSA.value,
                amount=settings.SUBSCRIPTION_PRICE_RUB,
                currency="RUB",
                description="Подписка Seller (1 мес)",
            )

            yookassa_payment = await yookassa.create_payment(
                amount=settings.SUBSCRIPTION_PRICE_RUB,
                currency="RUB",
                description="Подписка Seller - NetworkBot",
                metadata={
                    "payment_id": str(payment.id),
                    "user_id": str(user.id),
                    "type": "subscription",
                },
            )

            confirmation_url = yookassa_payment.get("confirmation", {}).get("confirmation_url", "")
            provider_id = yookassa_payment.get("id", "")

            await payment_service.update_payment_status(
                payment.id,
                PaymentStatus.PENDING.value,
                provider_payment_id=provider_id,
            )

        return {"status": "pending", "confirmation_url": confirmation_url}

    elif req.provider == "telegram":
        return {"status": "redirect_to_bot", "message": "Use bot /subscribe for Telegram Stars payment"}

    raise HTTPException(status_code=400, detail="Unknown provider")


# ========================
# Profile
# ========================

@router.get("/my/profile")
async def get_profile(user: User = Depends(require_user)):
    async with AsyncSessionLocal() as session:
        contacts_count = (await session.execute(
            select(func.count(Contact.id)).where(Contact.user_id == user.id)
        )).scalar()

        shares_count = (await session.execute(
            select(func.count(ContactShare.id)).where(
                ContactShare.owner_id == user.id,
                ContactShare.is_active == True,
            )
        )).scalar()

        purchases_count = (await session.execute(
            select(func.count(ContactPurchase.id)).where(ContactPurchase.buyer_id == user.id)
        )).scalar()

        sub_service = SubscriptionService(session)
        sub = await sub_service.get_active_subscription(user.id)

        profile_data = user.profile_data or {}

    return {
        "name": user.name,
        "username": profile_data.get("username"),
        "company": profile_data.get("company"),
        "job_title": profile_data.get("job_title"),
        "bio": profile_data.get("bio"),
        "contacts_count": contacts_count,
        "shares_count": shares_count,
        "purchases_count": purchases_count,
        "subscription_active": sub is not None and sub.status == SubscriptionStatus.ACTIVE.value,
        "is_admin": _is_admin(user),
    }


# ========================
# Admin (webapp)
# ========================

@router.get("/admin/stats")
async def webapp_admin_stats(user: User = Depends(require_user)):
    if not _is_admin(user):
        raise HTTPException(status_code=403, detail="Admin access required")

    async with AsyncSessionLocal() as session:
        users_count = (await session.execute(select(func.count(User.id)))).scalar()
        contacts_count = (await session.execute(select(func.count(Contact.id)))).scalar()
        active_subs = (await session.execute(
            select(func.count(Subscription.id)).where(
                Subscription.status == SubscriptionStatus.ACTIVE.value
            )
        )).scalar()
        active_shares = (await session.execute(
            select(func.count(ContactShare.id)).where(ContactShare.is_active == True)
        )).scalar()
        total_payments = (await session.execute(
            select(func.count(Payment.id)).where(Payment.status == PaymentStatus.SUCCEEDED.value)
        )).scalar()
        revenue = (await session.execute(
            select(func.sum(Payment.amount)).where(
                Payment.status == PaymentStatus.SUCCEEDED.value,
                Payment.currency == "RUB"
            )
        )).scalar() or 0

    return {
        "users": users_count,
        "contacts": contacts_count,
        "active_subscriptions": active_subs,
        "active_shares": active_shares,
        "successful_payments": total_payments,
        "revenue_rub": float(revenue),
    }


@router.get("/admin/users")
async def webapp_admin_users(
    limit: int = Query(50, ge=1, le=200),
    user: User = Depends(require_user),
):
    if not _is_admin(user):
        raise HTTPException(status_code=403, detail="Admin access required")

    async with AsyncSessionLocal() as session:
        stmt = select(User).order_by(User.created_at.desc()).limit(limit)
        result = await session.execute(stmt)
        users = result.scalars().all()

    return [
        {
            "id": str(u.id),
            "telegram_id": u.telegram_id,
            "name": u.name,
            "username": u.profile_data.get("username") if u.profile_data else None,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        }
        for u in users
    ]


@router.get("/admin/payments")
async def webapp_admin_payments(
    limit: int = Query(50, ge=1, le=200),
    user: User = Depends(require_user),
):
    if not _is_admin(user):
        raise HTTPException(status_code=403, detail="Admin access required")

    async with AsyncSessionLocal() as session:
        stmt = select(Payment).order_by(Payment.created_at.desc()).limit(limit)
        result = await session.execute(stmt)
        payments = result.scalars().all()

    return [
        {
            "id": str(p.id),
            "type": p.payment_type,
            "status": p.status,
            "provider": p.provider,
            "amount": f"{p.amount} {p.currency}",
            "created_at": p.created_at.isoformat() if p.created_at else None,
        }
        for p in payments
    ]
