"""Add progress tracking tables for lifelong learning

Revision ID: add_progress_tracking
Revises: c53687b1b4a9
Create Date: 2025-10-24 12:00:00.000000

"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

# revision identifiers, used by Alembic.
revision: str = "add_progress_tracking"
down_revision: Union[str, Sequence[str], None] = "c53687b1b4a9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create learning_sessions table
    op.create_table(
        "learning_sessions",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("subject", sa.String(100), nullable=False),
        sa.Column("topic", sa.String(200), nullable=False),
        sa.Column("duration_minutes", sa.Integer, nullable=True),
        sa.Column("session_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("performance_score", sa.Float, nullable=True),
        sa.Column("questions_asked", sa.Integer, default=0),
        sa.Column("difficulty_level", sa.Integer, nullable=True),
        sa.Column("session_metadata", JSONB, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), onupdate=sa.text("now()")),
    )

    # Create indexes for learning_sessions
    op.create_index("ix_learning_sessions_user_id", "learning_sessions", ["user_id"])
    op.create_index("ix_learning_sessions_subject", "learning_sessions", ["subject"])
    op.create_index(
        "ix_learning_sessions_session_date", "learning_sessions", ["session_date"]
    )
    op.create_index(
        "ix_learning_sessions_user_subject", "learning_sessions", ["user_id", "subject"]
    )

    # Create milestones table
    op.create_table(
        "milestones",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "milestone_type", sa.String(50), nullable=False
        ),  # 'topic_mastered', 'streak', 'difficulty_level_up'
        sa.Column("subject", sa.String(100), nullable=False),
        sa.Column("topic", sa.String(200), nullable=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("achieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("milestone_metadata", JSONB, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")
        ),
    )

    # Create indexes for milestones
    op.create_index("ix_milestones_user_id", "milestones", ["user_id"])
    op.create_index("ix_milestones_achieved_at", "milestones", ["achieved_at"])
    op.create_index("ix_milestones_user_subject", "milestones", ["user_id", "subject"])

    # Create consent_audit_log table
    op.create_table(
        "consent_audit_log",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "action", sa.String(50), nullable=False
        ),  # 'consent_granted', 'consent_revoked', 'level_changed', 'data_deleted'
        sa.Column("old_consent_level", sa.String(50), nullable=True),
        sa.Column("new_consent_level", sa.String(50), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.Text, nullable=True),
        sa.Column(
            "changed_at", sa.DateTime(timezone=True), server_default=sa.text("now()")
        ),
        sa.Column("details", JSONB, nullable=True),
    )

    # Create indexes for consent_audit_log
    op.create_index("ix_consent_audit_log_user_id", "consent_audit_log", ["user_id"])
    op.create_index(
        "ix_consent_audit_log_changed_at", "consent_audit_log", ["changed_at"]
    )

    # Add consent_level and data_retention fields to users table
    op.add_column(
        "users",
        sa.Column(
            "consent_level", sa.String(50), nullable=True, server_default="full_profile"
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "data_retention_days", sa.Integer, nullable=True, server_default="365"
        ),
    )
    op.add_column(
        "users",
        sa.Column("consent_granted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("last_consent_update", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Drop consent fields from users
    op.drop_column("users", "last_consent_update")
    op.drop_column("users", "consent_granted_at")
    op.drop_column("users", "data_retention_days")
    op.drop_column("users", "consent_level")

    # Drop consent_audit_log
    op.drop_index("ix_consent_audit_log_changed_at", table_name="consent_audit_log")
    op.drop_index("ix_consent_audit_log_user_id", table_name="consent_audit_log")
    op.drop_table("consent_audit_log")

    # Drop milestones
    op.drop_index("ix_milestones_user_subject", table_name="milestones")
    op.drop_index("ix_milestones_achieved_at", table_name="milestones")
    op.drop_index("ix_milestones_user_id", table_name="milestones")
    op.drop_table("milestones")

    # Drop learning_sessions
    op.drop_index("ix_learning_sessions_user_subject", table_name="learning_sessions")
    op.drop_index("ix_learning_sessions_session_date", table_name="learning_sessions")
    op.drop_index("ix_learning_sessions_subject", table_name="learning_sessions")
    op.drop_index("ix_learning_sessions_user_id", table_name="learning_sessions")
    op.drop_table("learning_sessions")
