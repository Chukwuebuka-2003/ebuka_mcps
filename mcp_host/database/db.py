from typing import AsyncGenerator
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from dotenv import load_dotenv
from contextlib import asynccontextmanager
from mcp_host.core.config import settings

# Load environment variables from .env file
load_dotenv()

# Retrieve the database URL from the environment
DATABASE_URL = settings.DATABASE_URL


# Create the asynchronous engine with future support.
async_engine = create_async_engine(
    DATABASE_URL,
    echo=True,  # Set to False in production.
    future=True,
)

#  For some functions we don't need async - this is async configuration
SYNC_DB_URL = settings.SYNC_DB_URL

sync_engine = create_engine(SYNC_DB_URL, echo=True, future=True)


# Configure the asynchronous session factory
AsyncSessionLocal = sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)

# Configure the synchronous session factory
SyncSessionLocal = sessionmaker(
    bind=sync_engine, expire_on_commit=False, autoflush=False, autocommit=False
)

# Base class for our ORM models.
Base = declarative_base()


# (via Depends)
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Yields a DB session for FastAPI dependency injection.
    """
    async with AsyncSessionLocal() as session:
        yield session


# For manual use (scripts, background tasks, agents)
@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Context manager for manual session use.
    Example:
        async with get_db_session() as db:
            ...
    """
    async with AsyncSessionLocal() as session:
        yield session


def get_sync_db() -> Session:
    """
    Returns a synchronous database session.
    """
    db = SyncSessionLocal()
    return db
