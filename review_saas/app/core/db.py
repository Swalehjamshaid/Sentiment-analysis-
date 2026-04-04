# filename: app/core/db.py
from __future__ import annotations
import os
import logging
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine, AsyncEngine
from sqlalchemy.orm import DeclarativeBase

# ------------------------------------------------------------------------------
# Logger
# ------------------------------------------------------------------------------
logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------
# 1. SHARED DECLARATIVE BASE
# ------------------------------------------------------------------------------
# Defined here to allow app.core.models to import it without circularity.
class Base(DeclarativeBase):
    """Declarative base for all SQLAlchemy models."""
    pass


# ------------------------------------------------------------------------------
# 2. CONFIGURATION & URL NORMALIZATION
# ------------------------------------------------------------------------------
def _get_db_url() -> str:
    """Normalizes DATABASE_URL for asyncpg (Postgres) or aiosqlite (SQLite)."""
    url = os.getenv("DATABASE_URL")
    
    if not url or not url.strip():
        logger.warning("DATABASE_URL environment variable is not set or empty. Falling back to SQLite test database.")
        return "sqlite+aiosqlite:///./test.db"
   
    url = url.strip()
    
    # Normalize postgres URLs for asyncpg driver
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql://") and "+asyncpg" not in url:
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    
    return url


DATABASE_URL: str = _get_db_url()


# ------------------------------------------------------------------------------
# 3. ENGINE & SESSION FACTORY
# ------------------------------------------------------------------------------
engine: AsyncEngine = create_async_engine(
    DATABASE_URL,
    echo=os.getenv("DEBUG", "false").lower() in {"1", "true", "yes"},
    future=True,
    pool_size=int(os.getenv("DB_POOL_SIZE", "10")),
    max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "20")),
)

SessionLocal = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


# ------------------------------------------------------------------------------
# 4. EXPORTS & INITIALIZATION
# ------------------------------------------------------------------------------
def get_engine() -> AsyncEngine:
    return engine


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for database sessions."""
    async with SessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_models() -> None:
    """
    Initializes database tables.
    Importing models LOCALLY prevents circular import crashes.
    """
    from app.core import models
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database models initialized successfully.")
    except Exception as e:
        logger.error("Failed to initialize database models", exc_info=True)
        raise
