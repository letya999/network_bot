import uuid
import enum
from sqlalchemy import Column, String, Text, ForeignKey, TIMESTAMP, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, backref
from app.db.base import Base

class InteractionType(str, enum.Enum):
    MET = "met"
    MESSAGE_SENT = "message_sent"
    MESSAGE_RECEIVED = "message_received"
    CALL = "call"
    MEETING = "meeting"

class Interaction(Base):
    __tablename__ = "interactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    contact_id = Column(UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False, index=True)
    type = Column(String, nullable=False) # or Enum
    date = Column(TIMESTAMP(timezone=True), server_default=func.now())
    notes = Column(Text)
    outcome = Column(Text)

    contact = relationship("Contact", backref=backref("interactions", cascade="all, delete-orphan"))
