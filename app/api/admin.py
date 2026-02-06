"""Admin API endpoints for dashboard and management."""
import hmac
import logging
from fastapi import APIRouter, Depends, HTTPException, Header, Query
from sqlalchemy import select, func
from app.db.session import AsyncSessionLocal
from app.models import User, Contact, Subscription, ContactShare, Payment
from app.models.subscription import SubscriptionStatus
from app.models.payment import PaymentStatus
from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


def verify_admin_token(x_admin_token: str = Header(None)):
    """Timing-safe token-based admin auth."""
    expected = settings.WEBHOOK_SECRET
    if not expected or not x_admin_token:
        raise HTTPException(status_code=403, detail="Forbidden")
    if not hmac.compare_digest(x_admin_token, expected):
        raise HTTPException(status_code=403, detail="Forbidden")
    return True


@router.get("/stats")
async def admin_stats(auth: bool = Depends(verify_admin_token)):
    """Get overall platform statistics."""
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
            select(func.count(Payment.id)).where(
                Payment.status == PaymentStatus.SUCCEEDED.value
            )
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


@router.get("/users")
async def admin_users(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    auth: bool = Depends(verify_admin_token),
):
    """List users."""
    async with AsyncSessionLocal() as session:
        stmt = select(User).order_by(User.created_at.desc()).limit(limit).offset(offset)
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


@router.get("/subscriptions")
async def admin_subscriptions(
    limit: int = Query(50, ge=1, le=200),
    auth: bool = Depends(verify_admin_token),
):
    """List subscriptions."""
    async with AsyncSessionLocal() as session:
        stmt = select(Subscription).order_by(Subscription.created_at.desc()).limit(limit)
        result = await session.execute(stmt)
        subs = result.scalars().all()

    return [
        {
            "id": str(s.id),
            "user_id": str(s.user_id),
            "plan": s.plan,
            "status": s.status,
            "provider": s.provider,
            "price": f"{s.price_amount} {s.price_currency}",
            "period_end": s.current_period_end.isoformat() if s.current_period_end else None,
        }
        for s in subs
    ]


@router.get("/payments")
async def admin_payments(
    limit: int = Query(50, ge=1, le=200),
    auth: bool = Depends(verify_admin_token),
):
    """List recent payments."""
    async with AsyncSessionLocal() as session:
        stmt = select(Payment).order_by(Payment.created_at.desc()).limit(limit)
        result = await session.execute(stmt)
        payments = result.scalars().all()

    return [
        {
            "id": str(p.id),
            "user_id": str(p.user_id),
            "type": p.payment_type,
            "status": p.status,
            "provider": p.provider,
            "amount": f"{p.amount} {p.currency}",
            "created_at": p.created_at.isoformat() if p.created_at else None,
        }
        for p in payments
    ]


@router.get("/shares")
async def admin_shares(
    limit: int = Query(50, ge=1, le=200),
    auth: bool = Depends(verify_admin_token),
):
    """List active shares."""
    async with AsyncSessionLocal() as session:
        stmt = (
            select(ContactShare)
            .where(ContactShare.is_active == True)
            .order_by(ContactShare.created_at.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        shares = result.scalars().all()

    return [
        {
            "id": str(s.id),
            "owner_id": str(s.owner_id),
            "contact_id": str(s.contact_id),
            "visibility": s.visibility,
            "price": f"{s.price_amount} {s.price_currency}",
            "views": s.view_count,
            "purchases": s.purchase_count,
        }
        for s in shares
    ]
