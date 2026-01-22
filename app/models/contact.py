import uuid
import enum
from sqlalchemy import Column, String, Text, ForeignKey, TIMESTAMP, Date, func, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, ARRAY, JSONB
from sqlalchemy.orm import relationship
from app.db.base import Base

class ContactStatus(str, enum.Enum):
    ACTIVE = "active"
    SLEEPING = "sleeping"
    ARCHIVED = "archived"

class Contact(Base):
    __tablename__ = "contacts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    company = Column(String(255))
    role = Column(String(255))
    phone = Column(String(50))
    telegram_username = Column(String(100))
    email = Column(String(255))
    linkedin_url = Column(String(500))
    event_name = Column(String(255))
    event_date = Column(Date)
    introduced_by_id = Column(UUID(as_uuid=True), ForeignKey("contacts.id"), nullable=True)
    what_looking_for = Column(Text)
    can_help_with = Column(Text)
    topics = Column(ARRAY(Text)) # Requires PostgreSQL
    agreements = Column(ARRAY(Text))
    follow_up_action = Column(Text)
    raw_transcript = Column(Text)
    status = Column(String, default=ContactStatus.ACTIVE.value)
    osint_data = Column(JSONB, default={})
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), onupdate=func.now(), server_default=func.now())

    user = relationship("User", backref="contacts")
    introduced_by = relationship("Contact", remote_side=[id])

    __table_args__ = (
        # Indexes are defined in spec but usually we define them via Column(index=True) or Index construct
        # contacts: (user_id), (user_id, status)
    )
