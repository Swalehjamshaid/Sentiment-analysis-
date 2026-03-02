
# filename: app/core/db.py
from __future__ import annotations
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.engine.url import make_url, URL
from app.core.config import settings

_engine: Optional[AsyncEngine] = None
_sessionmaker: Optional[async_sessionmaker[AsyncSession]] = None

def _normalize_async_url(raw_url: str) -> str:
    if not raw_url or not raw_url.strip():
        # default to sqlite if not provided
        return 'sqlite+aiosqlite:///./app.db'
    v = raw_url.strip().strip('"').strip("'")
    if v.startswith('postgres://'):
        v = v.replace('postgres://','postgresql://',1)
    if v.startswith('postgresql://'):
        v = v.replace('postgresql://','postgresql+asyncpg://',1)
    try:
        url: URL = make_url(v)
    except Exception as exc:
        raise ValueError('Invalid DATABASE_URL') from exc
    if url.port is not None and not isinstance(url.port, int):
        raise ValueError(f'Invalid port in DATABASE_URL: {url.port!r}')
    if url.drivername in {'postgresql','postgres'}:
        url = url.set(drivername='postgresql+asyncpg')
    return str(url)

def get_database_url() -> str:
    return _normalize_async_url(settings.DATABASE_URL or '')

def get_engine() -> AsyncEngine:
    global _engine, _sessionmaker
    if _engine is None:
        _engine = create_async_engine(get_database_url(), echo=settings.DEBUG, future=True)
        _sessionmaker = async_sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine

def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        get_engine()
    assert _sessionmaker is not None
    return _sessionmaker

@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    sm = get_sessionmaker()
    async with sm() as session:
        yield session
