# filename: app/core/db.py
from __future__ import annotations
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional
import os
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.engine.url import make_url
from sqlalchemy.exc import SQLAlchemyError
from app.core.config import settings
from app.core.models import Base  # Import your Base here

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
    Ensures the DATABASE_URL is compatible with SQLAlchemy's async drivers.
    Converts postgres:// to postgresql+asyncpg://
    """
    if not raw_url or not raw_url.strip():
        return 'sqlite+aiosqlite:///./app.db'

    v = raw_url.strip().strip('"').strip("'")

    # Replace old-style postgres URL
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
    """Retrieves the normalized URL from settings."""
    return _normalize_async_url(settings.DATABASE_URL or '')

# --------------------
# ENGINE & SESSION
# --------------------
def get_engine() -> AsyncEngine:
    """Returns the global AsyncEngine, initializing it if necessary."""
    global _engine, _sessionmaker
    if _engine is None:
        url = get_database_url()
        _engine = create_async_engine(
            url,
            echo=settings.DEBUG,
            future=True,
            pool_pre_ping=True,
        )
        _sessionmaker = async_sessionmaker(
            bind=_engine,
            expire_on_commit=False,
            class_=AsyncSession
        )
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Returns the global session factory."""
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
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# --------------------
# SAFE DATABASE INIT (FIXED: no auto-drop)
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
            # Safe: create tables if they don't exist
            await conn.run_sync(Base.metadata.create_all)
            print("✅ Database tables ensured (safe create - no data loss)")

            # Optional: print schema version
            print(f"Schema version in code: {SCHEMA_VERSION}")
        except SQLAlchemyError as e:
            print(f"⚠ Error initializing database: {e}")
            raise


# --------------------
# SESSION FACTORY FOR BACKGROUND TASKS
# --------------------
AsyncSessionLocal: async_sessionmaker[AsyncSession] = get_sessionmaker()
