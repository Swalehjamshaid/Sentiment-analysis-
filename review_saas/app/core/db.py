# filename: app/core/db.py
from __future__ import annotations
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.engine.url import make_url, URL
from app.core.config import settings
import os

_engine: Optional[AsyncEngine] = None
_sessionmaker: Optional[async_sessionmaker[AsyncSession]] = None


def _normalize_async_url(raw_url: str) -> str:
    if not raw_url or not raw_url.strip():
        raise ValueError(
            "DATABASE_URL is empty or not set! "
            "Check Railway variables → must be set to ${{Postgres.DATABASE_PRIVATE_URL}} "
            "or a valid postgresql+asyncpg:// URL"
        )

    v = raw_url.strip().strip('"').strip("'")

    # Normalize common Railway / Heroku-style postgres:// → postgresql+asyncpg://
    if v.startswith('postgres://'):
        v = v.replace('postgres://', 'postgresql+asyncpg://', 1)
    elif v.startswith('postgresql://'):
        v = v.replace('postgresql://', 'postgresql+asyncpg://', 1)

    try:
        url: URL = make_url(v)
    except Exception as exc:
        raise ValueError(f"Invalid DATABASE_URL format: {v}") from exc

    if url.port is not None and not isinstance(url.port, int):
        raise ValueError(f"Invalid port in DATABASE_URL: {url.port!r}")

    # Force asyncpg driver for PostgreSQL
    if url.drivername in {'postgresql', 'postgres'}:
        url = url.set(drivername='postgresql+asyncpg')

    # Optional: warn if not postgres
    if not url.drivername.startswith('postgresql+asyncpg'):
        print(f"WARNING: Using non-PostgreSQL driver: {url.drivername}")

    return str(url)


def get_database_url() -> str:
    raw = settings.DATABASE_URL or os.environ.get("DATABASE_URL", "")
    print("get_database_url() → raw input =", repr(raw))           # debug
    final = _normalize_async_url(raw)
    print("get_database_url() → final normalized =", final)       # debug
    return final


def get_engine() -> AsyncEngine:
    global _engine, _sessionmaker
    if _engine is None:
        url = get_database_url()
        _engine = create_async_engine(
            url,
            echo=settings.DEBUG,
            future=True,
            pool_pre_ping=True,          # recommended for Railway / containers
        )
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
