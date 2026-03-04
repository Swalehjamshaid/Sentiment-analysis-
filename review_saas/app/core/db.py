# filename: app/core/db.py
from __future__ import annotations
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.engine.url import make_url
from sqlalchemy.exc import SQLAlchemyError
from app.core.config import settings

_engine: Optional[AsyncEngine] = None
_sessionmaker: Optional[async_sessionmaker[AsyncSession]] = None

def _normalize_async_url(raw_url: str) -> str:
    if not raw_url or not raw_url.strip():
        return 'sqlite+aiosqlite:///./app.db'
    
    v = raw_url.strip().strip('"').strip("'")
    
    if v.startswith('postgres://'):
        v = v.replace('postgres://', 'postgresql://', 1)
    if v.startswith('postgresql://'):
        v = v.replace('postgresql://', 'postgresql+asyncpg://', 1)
    
    try:
        url = make_url(v)
        if url.drivername in ('postgresql', 'postgres'):
            v = str(url.set(drivername='postgresql+asyncpg'))
    except Exception as exc:
        raise ValueError(f'Invalid DATABASE_URL provided: {raw_url}') from exc
        
    return v

def get_database_url() -> str:
    return _normalize_async_url(settings.DATABASE_URL or '')

def get_engine() -> AsyncEngine:
    global _engine, _sessionmaker
    if _engine is None:
        url = get_database_url()
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
    if _sessionmaker is None:
        get_engine()
    return _sessionmaker

@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    """Transactional scope for the session."""
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


# 🔹 DEV ONLY: Wipe and recreate all tables on startup
async def reset_database(Base):
    """
    Drops all tables and recreates them.
    Only for development/testing environments.
    """
    engine = get_engine()
    async with engine.begin() as conn:
        try:
            print("Dropping all tables...")
            await conn.run_sync(Base.metadata.drop_all)
            print("Creating fresh tables...")
            await conn.run_sync(Base.metadata.create_all)
            print("Database reset complete ✅")
        except SQLAlchemyError as e:
            print(f"Error resetting database: {e}")
