import uuid
from sqlalchemy import Column, String, Text, ForeignKey, TIMESTAMP, Integer, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import Base

class Match(Base):
    __tablename__ = "matches"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    contact_a_id = Column(UUID(as_uuid=True), ForeignKey("contacts.id"), nullable=False)
    contact_b_id = Column(UUID(as_uuid=True), ForeignKey("contacts.id"), nullable=False)
    
    score = Column(Integer, default=0)
    synergy_summary = Column(Text)
    suggested_pitch = Column(Text)
    
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    expires_at = Column(TIMESTAMP(timezone=True))

    __table_args__ = (
        UniqueConstraint('contact_a_id', 'contact_b_id', name='uq_match_contacts'),
    )
