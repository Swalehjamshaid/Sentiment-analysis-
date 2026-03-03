# filename: app/core/db.py
from __future__ import annotations
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional
import os

from sqlalchemy.ext.asyncio import (
    AsyncEngine, 
    create_async_engine, 
    async_sessionmaker, 
    AsyncSession
)
from sqlalchemy.engine.url import make_url
from app.core.config import settings

# Global instances for reuse
_engine: Optional[AsyncEngine] = None
_sessionmaker: Optional[async_sessionmaker[AsyncSession]] = None

def _normalize_async_url(raw_url: str) -> str:
    """
    Ensures the DATABASE_URL is compatible with SQLAlchemy's async drivers.
    Converts postgres:// to postgresql+asyncpg://
    """
    if not raw_url or not raw_url.strip():
        # Fallback to local SQLite if no URL is provided
        return 'sqlite+aiosqlite:///./app.db'
    
    # Clean the URL from potential quotes or whitespace
    v = raw_url.strip().strip('"').strip("'")
    
    # Railway/Heroku style fix: replace postgres:// with postgresql://
    if v.startswith('postgres://'):
        v = v.replace('postgres://', 'postgresql://', 1)
    
    # Add the asyncpg driver if it's a postgresql URL
    if v.startswith('postgresql://'):
        v = v.replace('postgresql://', 'postgresql+asyncpg://', 1)
    
    # Final check for driver consistency
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

def get_engine() -> AsyncEngine:
    """Returns the global AsyncEngine, initializing it if necessary."""
    global _engine, _sessionmaker
    if _engine is None:
        url = get_database_url()
        # pool_pre_ping helps maintain connections to Railway Postgres
        _engine = create_async_engine(
            url, 
            echo=settings.DEBUG, 
            future=True,
            pool_pre_ping=True
        )
        _sessionmaker = async_sessionmaker(
            bind=_engine, 
            expire_on_commit=False,
            class_=AsyncSession
        )
    return _engine

def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Returns the global session factory."""
    if _sessionmaker is None:
        get_engine()
    return _sessionmaker

@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    """Provides a transactional scope for the database session."""
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
