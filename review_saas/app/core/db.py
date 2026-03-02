# filename: app/core/db.py
from __future__ import annotations
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional
import os

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.engine.url import make_url, URL
from app.core.config import settings


_engine: Optional[AsyncEngine] = None
_sessionmaker: Optional[async_sessionmaker[AsyncSession]] = None


def _normalize_async_url(raw_url: str) -> str:
    """
    Normalize the database URL and force asyncpg driver for PostgreSQL.
    In production: fail loudly if URL is missing → do NOT fallback to SQLite.
    """
    if not raw_url or not raw_url.strip():
        # In production we want to crash early with clear message
        env_name = "DATABASE_URL"
        if os.getenv("ENVIRONMENT") == "production":
            raise ValueError(
                f"{env_name} is empty or not set in production environment!\n"
                "→ Check Railway Variables tab\n"
                "→ Should be set to: ${{Postgres.DATABASE_PRIVATE_URL}} or ${{Postgres.DATABASE_URL}}\n"
                "→ Or manually paste the real value from your Postgres service credentials"
            )
        # Only allow SQLite fallback in local/development (if you really want it)
        print("WARNING: DATABASE_URL not set → falling back to local SQLite (development only)")
        return 'sqlite+aiosqlite:///./app.db'

    v = raw_url.strip().strip('"').strip("'")

    # Railway often gives postgres:// → convert to postgresql+asyncpg://
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

    # Force asyncpg driver (required for async PostgreSQL)
    if url.drivername in {'postgresql', 'postgres'}:
        url = url.set(drivername='postgresql+asyncpg')

    normalized = str(url)
    print(f"Normalized database URL: {normalized}")  # helpful in logs
    return normalized


def get_database_url() -> str:
    # Prefer settings.DATABASE_URL (from pydantic), fallback to os.environ
    raw_url = settings.DATABASE_URL or os.environ.get("DATABASE_URL", "")
    return _normalize_async_url(raw_url)


def get_engine() -> AsyncEngine:
    global _engine, _sessionmaker
    if _engine is None:
        url = get_database_url()
        _engine = create_async_engine(
            url,
            echo=settings.DEBUG,
            future=True,
            pool_pre_ping=True,           # recommended for Railway / containers
            pool_size=5,
            max_overflow=10,
        )
        _sessionmaker = async_sessionmaker(
            bind=_engine,
            expire_on_commit=False,
            autoflush=False,
        )
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
