"""convert_datetime_columns_to_timestamptz

Revision ID: 845ee70baa51
Revises: b6e7fe2a0944
Create Date: 2025-10-30 09:05:01.440280

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '845ee70baa51'
down_revision: Union[str, Sequence[str], None] = 'b6e7fe2a0944'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Convert all TIMESTAMP WITHOUT TIME ZONE columns to TIMESTAMP WITH TIME ZONE."""
    # File uploads table
    op.execute("ALTER TABLE file_uploads ALTER COLUMN created_at TYPE TIMESTAMP WITH TIME ZONE USING created_at AT TIME ZONE 'UTC'")
    op.execute("ALTER TABLE file_uploads ALTER COLUMN updated_at TYPE TIMESTAMP WITH TIME ZONE USING updated_at AT TIME ZONE 'UTC'")

    # Chat sessions table
    op.execute("ALTER TABLE chat_sessions ALTER COLUMN created_at TYPE TIMESTAMP WITH TIME ZONE USING created_at AT TIME ZONE 'UTC'")
    op.execute("ALTER TABLE chat_sessions ALTER COLUMN updated_at TYPE TIMESTAMP WITH TIME ZONE USING updated_at AT TIME ZONE 'UTC'")

    # Chat messages table
    op.execute("ALTER TABLE chat_messages ALTER COLUMN created_at TYPE TIMESTAMP WITH TIME ZONE USING created_at AT TIME ZONE 'UTC'")
    op.execute("ALTER TABLE chat_messages ALTER COLUMN updated_at TYPE TIMESTAMP WITH TIME ZONE USING updated_at AT TIME ZONE 'UTC'")


def downgrade() -> None:
    """Convert all TIMESTAMP WITH TIME ZONE columns back to TIMESTAMP WITHOUT TIME ZONE."""
    # File uploads table
    op.execute("ALTER TABLE file_uploads ALTER COLUMN created_at TYPE TIMESTAMP WITHOUT TIME ZONE")
    op.execute("ALTER TABLE file_uploads ALTER COLUMN updated_at TYPE TIMESTAMP WITHOUT TIME ZONE")

    # Chat sessions table
    op.execute("ALTER TABLE chat_sessions ALTER COLUMN created_at TYPE TIMESTAMP WITHOUT TIME ZONE")
    op.execute("ALTER TABLE chat_sessions ALTER COLUMN updated_at TYPE TIMESTAMP WITHOUT TIME ZONE")

    # Chat messages table
    op.execute("ALTER TABLE chat_messages ALTER COLUMN created_at TYPE TIMESTAMP WITHOUT TIME ZONE")
    op.execute("ALTER TABLE chat_messages ALTER COLUMN updated_at TYPE TIMESTAMP WITHOUT TIME ZONE")
