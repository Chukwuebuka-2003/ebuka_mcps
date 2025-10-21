from logging.config import fileConfig
import sys
from pathlib import Path
import asyncio

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# Add the project base directory to sys.path for module resolution
BASE_PATH = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_PATH))
from mcp_host.database.db import Base, async_engine
from mcp_host.core.config import settings
import mcp_host.models

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


DATABASE_URL = settings.DATABASE_URL
if not DATABASE_URL:
    raise ValueError("DATABASE_URL is not set")

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url") or DATABASE_URL
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_migrations(sync_connection):
    """
    Perform the migration run in 'online' mode.

    This function is executed in a synchronous context by SQLAlchemy's run_sync method.
    """
    context.configure(
        connection=sync_connection,
        target_metadata=target_metadata,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online():
    """
    Run migrations in 'online' mode using an asynchronous connection.
    """
    async with async_engine.connect() as connection:
        # Run the synchronous migration function within the async connection context
        await connection.run_sync(do_migrations)


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
