"""
Updated User model with consent management fields
"""

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
    func,
)
from mcp_host.database.db import Base
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
import uuid


class User(Base):
    """Table to store user metadata with consent management."""

    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    email = Column(String, nullable=False, unique=True)
    phone_number = Column(String, nullable=False)
    password_hash = Column(String, nullable=True)

    # Consent and privacy fields
    consent_level = Column(
        String(50), nullable=True, default="full_profile"
    )  # 'full_profile', 'limited_anonymized', 'minimal_pseudonymous'
    data_retention_days = Column(
        Integer, nullable=True, default=365
    )  # How long to keep data
    consent_granted_at = Column(DateTime(timezone=True), nullable=True)
    last_consent_update = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<User {self.name}>"
