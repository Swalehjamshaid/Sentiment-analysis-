# filename: app/core/db.py
from __future__ import annotations
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional
import os
import logging

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    create_async_engine,
    async_sessionmaker,
    AsyncSession
)
from sqlalchemy.engine.url import make_url
from sqlalchemy.exc import SQLAlchemyError
from app.core.config import settings
from app.core.models import Base  # Make sure Base includes all models like Review

# --------------------
# Setup logger
# --------------------
logger = logging.getLogger("app.db")
logging.basicConfig(level=logging.INFO)

# --------------------
# Global instances for reuse
# --------------------
_engine: Optional[AsyncEngine] = None
_sessionmaker: Optional[async_sessionmaker[AsyncSession]] = None

# --------------------
# URL NORMALIZATION
# --------------------
def _normalize_async_url(raw_url: str) -> str:
    """
    Ensures DATABASE_URL is compatible with SQLAlchemy async drivers.
    Converts postgres:// to postgresql+asyncpg://
    """
    if not raw_url or not raw_url.strip():
        return 'sqlite+aiosqlite:///./app.db'

    v = raw_url.strip().strip('"').strip("'")

    # Convert old-style postgres URL
    if v.startswith('postgres://'):
        v = v.replace('postgres://', 'postgresql://', 1)
    if v.startswith('postgresql://') and 'asyncpg' not in v:
        v = v.replace('postgresql://', 'postgresql+asyncpg://', 1)

    try:
        url = make_url(v)
        if url.drivername in ('postgresql', 'postgres'):
            v = str(url.set(drivername='postgresql+asyncpg'))
    except Exception as exc:
        raise ValueError(f'Invalid DATABASE_URL provided: {raw_url}') from exc

    return v


def get_database_url() -> str:
    """Returns normalized DATABASE_URL from settings or environment."""
    env_url = getattr(settings, "DATABASE_URL", os.getenv("DATABASE_URL", ""))
    return _normalize_async_url(env_url)

# --------------------
# ENGINE & SESSION
# --------------------
def get_engine() -> AsyncEngine:
    """Returns global AsyncEngine, initializing if needed."""
    global _engine, _sessionmaker
    if _engine is None:
        url = get_database_url()
        logger.info(f"Initializing AsyncEngine with URL: {url}")
        _engine = create_async_engine(
            url,
            echo=getattr(settings, "DEBUG", False),
            future=True,
            pool_pre_ping=True,
            pool_size=10,
            max_overflow=20
        )
        _sessionmaker = async_sessionmaker(
            bind=_engine,
            expire_on_commit=False,
            class_=AsyncSession
        )
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Returns global session factory."""
    global _sessionmaker
    if _sessionmaker is None:
        get_engine()
    return _sessionmaker


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    """
    Provides a transactional scope for the database session.
    Commits if successful, rolls back if exception occurs.
    """
    session_factory = get_sessionmaker()
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
            logger.info("✅ Session committed successfully.")
        except Exception as e:
            await session.rollback()
            logger.error(f"⚠ Session rollback due to error: {e}")
            raise
        finally:
            await session.close()
            logger.info("Session closed.")


# --------------------
# SAFE DATABASE INIT (no auto-drop)
# --------------------
async def init_database():
    """
    Safe initialization: creates missing tables only.
    Does NOT drop existing tables or data.
    Logs schema version for awareness.
    """
    from app.core.models import SCHEMA_VERSION  # Avoid circular import

    engine = get_engine()
    async with engine.begin() as conn:
        try:
            # Create missing tables
            await conn.run_sync(Base.metadata.create_all)
            logger.info("✅ Database tables ensured (safe create - no data loss)")
            logger.info(f"Schema version in code: {SCHEMA_VERSION}")
        except SQLAlchemyError as e:
            logger.error(f"⚠ Error initializing database: {e}")
            raise

# --------------------
# SESSION FACTORY FOR BACKGROUND TASKS
# --------------------
AsyncSessionLocal: async_sessionmaker[AsyncSession] = get_sessionmaker()
