import uuid
import enum
from sqlalchemy import Column, String, Text, Index, ForeignKey, DateTime, Boolean, Integer, Numeric, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from app.db.base import Base


class SubscriptionPlan(str, enum.Enum):
    FREE = "free"
    SELLER = "seller"          # Can share/sell contacts
    SELLER_PRO = "seller_pro"  # Extended limits


class SubscriptionStatus(str, enum.Enum):
    ACTIVE = "active"
    CANCELLED = "cancelled"
    PAST_DUE = "past_due"
    EXPIRED = "expired"


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    plan = Column(String(50), default=SubscriptionPlan.FREE.value, nullable=False)
    status = Column(String(50), default=SubscriptionStatus.ACTIVE.value, nullable=False)

    # Payment provider info
    provider = Column(String(50))  # yookassa, telegram, cardpay
    provider_subscription_id = Column(String(255))  # External subscription ID
    provider_customer_id = Column(String(255))

    # Billing
    price_amount = Column(Numeric(10, 2), default=0)
    price_currency = Column(String(3), default="RUB")
    billing_cycle_days = Column(Integer, default=30)

    current_period_start = Column(DateTime(timezone=True))
    current_period_end = Column(DateTime(timezone=True))
    next_payment_at = Column(DateTime(timezone=True))

    # Metadata
    metadata_ = Column("metadata", JSONB, default={})
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    user = relationship("User", backref="subscriptions")

    __table_args__ = (
        Index('ix_subscription_user_status', 'user_id', 'status'),
    )
