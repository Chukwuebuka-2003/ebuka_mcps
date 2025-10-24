"""
SQLAlchemy models for lifelong learning progress tracking
"""

from datetime import datetime
from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
    ForeignKey,
    Float,
    JSON,
    func,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from mcp_host.database.db import Base
from sqlalchemy.orm import relationship
import uuid


class LearningSession(Base):
    """Tracks individual learning sessions for progress analysis"""

    __tablename__ = "learning_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    subject = Column(String(100), nullable=False)
    topic = Column(String(200), nullable=False)
    duration_minutes = Column(Integer, nullable=True)
    session_date = Column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    performance_score = Column(Float, nullable=True)  # 0.0 to 1.0
    questions_asked = Column(Integer, default=0)
    difficulty_level = Column(Integer, nullable=True)
    session_metadata = Column(JSONB, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationship
    user = relationship("User", backref="learning_sessions")

    def __repr__(self):
        return f"<LearningSession {self.user_id} - {self.subject}/{self.topic} on {self.session_date}>"


class Milestone(Base):
    """Tracks student achievements and milestones"""

    __tablename__ = "milestones"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    milestone_type = Column(
        String(50), nullable=False
    )  # 'topic_mastered', 'streak', 'difficulty_level_up'
    subject = Column(String(100), nullable=False)
    topic = Column(String(200), nullable=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    achieved_at = Column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    milestone_metadata = Column(JSONB, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationship
    user = relationship("User", backref="milestones")

    def __repr__(self):
        return f"<Milestone {self.user_id} - {self.title}>"


class ConsentAuditLog(Base):
    """Audit log for consent changes (GDPR compliance)"""

    __tablename__ = "consent_audit_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    action = Column(
        String(50), nullable=False
    )  # 'consent_granted', 'consent_revoked', 'level_changed'
    old_consent_level = Column(String(50), nullable=True)
    new_consent_level = Column(String(50), nullable=True)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(Text, nullable=True)
    changed_at = Column(DateTime(timezone=True), server_default=func.now())
    details = Column(JSONB, nullable=True)

    # Relationship
    user = relationship("User", backref="consent_logs")

    def __repr__(self):
        return f"<ConsentAuditLog {self.user_id} - {self.action} at {self.changed_at}>"
