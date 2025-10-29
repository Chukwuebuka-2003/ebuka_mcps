from datetime import datetime
from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
    ForeignKey,
    Boolean,
    JSON,
    Enum as SQLEnum,
)
from mcp_host.database.db import Base
from sqlalchemy.orm import relationship
import enum


class FileUploadStatus(str, enum.Enum):
    """Status enum for file upload tracking."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class FileUpload(Base):
    """File upload tracking model for monitoring processing status."""

    __tablename__ = "file_uploads"

    id = Column(String(100), primary_key=True, index=True)
    user_id = Column(String(100), index=True, nullable=False)
    filename = Column(String(500), nullable=False)
    subject = Column(String(100), nullable=False)
    topic = Column(String(200), nullable=False)
    status = Column(SQLEnum(FileUploadStatus), default=FileUploadStatus.PENDING, nullable=False)
    blob_name = Column(String(500), nullable=True)
    chunks_processed = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ChatSession(Base):
    """Chat session model representing a conversation."""

    __tablename__ = "chat_sessions"

    id = Column(Integer, primary_key=True, index=True)
    chat_session_id = Column(String(100), unique=True, index=True, nullable=False)
    user_id = Column(String(100), index=True, nullable=True)
    title = Column(String(200), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    messages = relationship(
        "ChatMessage", back_populates="session", cascade="all, delete-orphan"
    )


class ChatMessage(Base):
    """Chat message model representing individual messages in a conversation."""

    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    chat_session_id = Column(
        String(100), ForeignKey("chat_sessions.chat_session_id"), nullable=False
    )
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    message_metadata = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    session = relationship("ChatSession", back_populates="messages")
