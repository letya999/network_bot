import uuid
import enum
from sqlalchemy import Column, String, Text, ForeignKey, DateTime, Boolean, func, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from sqlalchemy.orm import relationship
from app.db.base import Base


class ShareVisibility(str, enum.Enum):
    PUBLIC = "public"           # Visible to anyone with link
    PRIVATE = "private"         # Only visible to specific users
    PAID = "paid"               # Visible after payment


class ContactShare(Base):
    """Represents a contact that the owner has shared/published."""
    __tablename__ = "contact_shares"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    contact_id = Column(UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False, index=True)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)

    # Visibility
    visibility = Column(String(50), default=ShareVisibility.PUBLIC.value, nullable=False)
    allowed_user_ids = Column(ARRAY(UUID(as_uuid=True)), default=[])  # For PRIVATE visibility

    # Which fields are visible (null = all visible)
    visible_fields = Column(ARRAY(Text), default=[])  # e.g. ["name", "company", "phone"]
    hidden_fields = Column(ARRAY(Text), default=[])    # Fields explicitly hidden

    # Pricing (for PAID visibility)
    price_amount = Column(String(20), default="0")  # String for flexibility
    price_currency = Column(String(3), default="RUB")

    # Share metadata
    description = Column(Text)  # Owner's description/note about this contact
    share_token = Column(String(64), unique=True, index=True)  # Unique link token
    is_active = Column(Boolean, default=True)

    # Stats
    view_count = Column(String(20), default="0")
    purchase_count = Column(String(20), default="0")

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    contact = relationship("Contact", backref="shares")
    owner = relationship("User", backref="shared_contacts")

    __table_args__ = (
        Index('ix_share_owner_active', 'owner_id', 'is_active'),
        Index('ix_share_visibility', 'visibility', 'is_active'),
    )


class ContactPurchase(Base):
    """Records when a user buys/receives access to a shared contact."""
    __tablename__ = "contact_purchases"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    share_id = Column(UUID(as_uuid=True), ForeignKey("contact_shares.id"), nullable=False, index=True)
    buyer_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    seller_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    # The contact copy created in buyer's account
    copied_contact_id = Column(UUID(as_uuid=True), ForeignKey("contacts.id"), nullable=True)

    # Payment info
    payment_id = Column(UUID(as_uuid=True), ForeignKey("payments.id"), nullable=True)
    amount_paid = Column(String(20), default="0")
    currency = Column(String(3), default="RUB")

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    share = relationship("ContactShare", backref="purchases")
    buyer = relationship("User", foreign_keys=[buyer_id], backref="purchased_contacts")
    seller = relationship("User", foreign_keys=[seller_id])
    copied_contact = relationship("Contact", foreign_keys=[copied_contact_id])

    __table_args__ = (
        Index('ix_purchase_buyer', 'buyer_id', 'share_id'),
    )
