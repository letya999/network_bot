import logging
import uuid
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.subscription import Subscription, SubscriptionPlan, SubscriptionStatus

logger = logging.getLogger(__name__)


class SubscriptionService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_active_subscription(self, user_id: uuid.UUID) -> Subscription | None:
        stmt = select(Subscription).where(
            Subscription.user_id == user_id,
            Subscription.status == SubscriptionStatus.ACTIVE.value,
        ).order_by(Subscription.created_at.desc())
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def has_seller_access(self, user_id: uuid.UUID) -> bool:
        sub = await self.get_active_subscription(user_id)
        if not sub:
            return False
        if sub.plan in (SubscriptionPlan.SELLER.value, SubscriptionPlan.SELLER_PRO.value):
            if sub.current_period_end and sub.current_period_end > datetime.utcnow():
                return True
            # Grace period: 3 days after expiry
            if sub.current_period_end:
                grace = sub.current_period_end + timedelta(days=3)
                if datetime.utcnow() < grace:
                    return True
        return False

    async def create_subscription(
        self,
        user_id: uuid.UUID,
        plan: str = SubscriptionPlan.SELLER.value,
        provider: str = "yookassa",
        provider_subscription_id: str = None,
        price_amount: float = 990,
        price_currency: str = "RUB",
        billing_cycle_days: int = 30,
    ) -> Subscription:
        now = datetime.utcnow()
        sub = Subscription(
            user_id=user_id,
            plan=plan,
            status=SubscriptionStatus.ACTIVE.value,
            provider=provider,
            provider_subscription_id=provider_subscription_id,
            price_amount=price_amount,
            price_currency=price_currency,
            billing_cycle_days=billing_cycle_days,
            current_period_start=now,
            current_period_end=now + timedelta(days=billing_cycle_days),
            next_payment_at=now + timedelta(days=billing_cycle_days),
        )
        self.session.add(sub)
        await self.session.commit()
        await self.session.refresh(sub)
        return sub

    async def renew_subscription(self, subscription_id: uuid.UUID) -> Subscription | None:
        result = await self.session.execute(
            select(Subscription).where(Subscription.id == subscription_id)
        )
        sub = result.scalars().first()
        if not sub:
            return None

        now = datetime.utcnow()
        sub.status = SubscriptionStatus.ACTIVE.value
        sub.current_period_start = now
        sub.current_period_end = now + timedelta(days=sub.billing_cycle_days or 30)
        sub.next_payment_at = sub.current_period_end
        await self.session.commit()
        await self.session.refresh(sub)
        return sub

    async def cancel_subscription(self, subscription_id: uuid.UUID) -> Subscription | None:
        result = await self.session.execute(
            select(Subscription).where(Subscription.id == subscription_id)
        )
        sub = result.scalars().first()
        if not sub:
            return None

        sub.status = SubscriptionStatus.CANCELLED.value
        await self.session.commit()
        await self.session.refresh(sub)
        return sub

    async def mark_expired(self, subscription_id: uuid.UUID) -> None:
        result = await self.session.execute(
            select(Subscription).where(Subscription.id == subscription_id)
        )
        sub = result.scalars().first()
        if sub:
            sub.status = SubscriptionStatus.EXPIRED.value
            await self.session.commit()

    async def get_expiring_subscriptions(self, within_days: int = 3):
        """Get subscriptions expiring within N days for renewal reminders."""
        cutoff = datetime.utcnow() + timedelta(days=within_days)
        stmt = select(Subscription).where(
            Subscription.status == SubscriptionStatus.ACTIVE.value,
            Subscription.current_period_end <= cutoff,
            Subscription.current_period_end > datetime.utcnow(),
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()
