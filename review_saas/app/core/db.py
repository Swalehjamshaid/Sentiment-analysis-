
# filename: app/core/db.py
from __future__ import annotations
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.engine.url import make_url, URL
from app.core.config import settings

_engine: Optional[AsyncEngine] = None


def _normalize_async_url(raw_url: str) -> str:
    if not raw_url or not raw_url.strip():
        raise ValueError(
            "DATABASE_URL is empty. Set a valid value, e.g.: "
            "postgresql+asyncpg://user:pass@host:5432/dbname?sslmode=require"
        )
    v = raw_url.strip().strip('"').strip("'")
    if v.startswith("sqlite+aiosqlite://"):
        return v
    if v.startswith("postgres://"):
        v = v.replace("postgres://", "postgresql://", 1)
    if v.startswith("postgresql://"):
        v = v.replace("postgresql://", "postgresql+asyncpg://", 1)
    try:
        url: URL = make_url(v)
    except Exception as exc:
        raise ValueError(
            "Invalid DATABASE_URL. Example: "
            "postgresql+asyncpg://user:pass@host:5432/dbname?sslmode=require"
        ) from exc
    if url.port is not None and not isinstance(url.port, int):
        raise ValueError(f"Invalid port in DATABASE_URL: {url.port!r}. Use numeric like 5432.")
    if url.drivername in {"postgresql", "postgres"}:
        url = url.set(drivername="postgresql+asyncpg")
    return str(url)


def get_database_url() -> str:
    raw: Optional[str] = settings.DATABASE_URL or settings.DATABASE_PUBLIC_URL
    if not raw:
        raise ValueError("DATABASE_URL is empty. Please set it in your environment or .env file.")
    return _normalize_async_url(raw)


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        normalized = get_database_url()
        _engine = create_async_engine(
            normalized,
            echo=settings.DEBUG,
            future=True,
        )
    return _engine
