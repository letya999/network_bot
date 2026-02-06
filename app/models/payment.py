import uuid
import enum
from sqlalchemy import Column, String, Text, Index, ForeignKey, DateTime, Numeric, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from app.db.base import Base


class PaymentStatus(str, enum.Enum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"
    FAILED = "failed"


class PaymentType(str, enum.Enum):
    CONTACT_PURCHASE = "contact_purchase"
    SUBSCRIPTION = "subscription"
    SUBSCRIPTION_RENEWAL = "subscription_renewal"


class PaymentProvider(str, enum.Enum):
    YOOKASSA = "yookassa"
    TELEGRAM = "telegram"        # Telegram Payments (Stars)
    CARDPAY = "cardpay"          # CardPay/Unlimint


class Payment(Base):
    __tablename__ = "payments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)

    # Payment type & status
    payment_type = Column(String(50), nullable=False)
    status = Column(String(50), default=PaymentStatus.PENDING.value, nullable=False)
    provider = Column(String(50), nullable=False)

    # Amount
    amount = Column(Numeric(10, 2), nullable=False)
    currency = Column(String(3), default="RUB", nullable=False)

    # Provider references
    provider_payment_id = Column(String(255), index=True)  # External payment ID
    provider_data = Column(JSONB, default={})   # Raw provider response

    # Description
    description = Column(Text)

    # Linked entities
    subscription_id = Column(UUID(as_uuid=True), ForeignKey("subscriptions.id"), nullable=True)
    contact_share_id = Column(UUID(as_uuid=True), ForeignKey("contact_shares.id"), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    user = relationship("User", backref="payments")
    subscription = relationship("Subscription", backref="payments")
    contact_share = relationship("ContactShare", backref="payments")

    __table_args__ = (
        Index('ix_payment_user_status', 'user_id', 'status'),
        Index('ix_payment_status', 'status'),
    )
