# filename: app/core/db.py
"""
Async SQLAlchemy database setup for the ReviewSaaS backend.

- Reads DATABASE_URL from environment (supports postgres://, postgresql://,
  postgresql+asyncpg://; auto-normalizes to asyncpg)
- Creates an async Engine and Session factory
- Provides FastAPI dependency `get_session`
- Exposes `init_models()` to create tables at startup (for environments without Alembic)

Usage (FastAPI):
---------------
from fastapi import FastAPI
from app.core.db import init_models
from app.routes.companies import router as companies_router
from app.routes.reviews import router as reviews_router

app = FastAPI()

@app.on_event("startup")
async def on_startup():
    await init_models()

app.include_router(companies_router)
app.include_router(reviews_router)

Environment:
------------
DATABASE_URL=postgresql://user:password@host:5432/dbname
  (This module auto-converts to postgresql+asyncpg://)

Dependencies:
-------------
pip install sqlalchemy asyncpg
"""

from __future__ import annotations

import os
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine, AsyncEngine
from sqlalchemy.orm import DeclarativeBase


# ---------------------------
# Configuration / URL handling
# ---------------------------

def _get_env(key: str, default: str | None = None) -> str:
    value = os.getenv(key, default)
    if value is None or not str(value).strip():
        raise RuntimeError(
            f"Missing required environment variable: {key}. "
            f"Example: postgresql://user:pass@localhost:5432/reviewsdb"
        )
    return str(value)


def _normalize_db_url(url: str) -> str:
    """
    Ensure async dialect is used.
    - postgres:// -> postgresql+asyncpg://
    - postgresql:// -> postgresql+asyncpg:// (if not already)
    """
    url = url.strip()
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    if url.startswith("postgresql://") and "+asyncpg" not in url:
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


DATABASE_URL: str = _normalize_db_url(_get_env("DATABASE_URL"))


# ---------------------------
# SQLAlchemy base / engine / session
# ---------------------------

class Base(DeclarativeBase):
    """Declarative base for SQLAlchemy models."""
    pass


# You can tune pool settings per your workload
engine = create_async_engine(
    DATABASE_URL,
    echo=os.getenv("DEBUG", "false").lower() in {"1", "true", "yes"},
    future=True,
    pool_size=int(os.getenv("DB_POOL_SIZE", "10")),
    max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "20")),
)

# Factory for AsyncSession instances
SessionLocal = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


# ---------------------------
# FastAPI dependency
# ---------------------------

async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that yields an AsyncSession.
    Closes the session automatically after use.
    """
    async with SessionLocal() as session:
        try:
            yield session
        finally:
            # Explicit close is defensive; context manager already handles it.
            await session.close()


# ---------------------------
# Initialization helper
# ---------------------------

async def init_models() -> None:
    """
    Create tables from SQLAlchemy models.

    NOTE:
    - For production, prefer Alembic migrations.
    - This function imports `app.core.models` to ensure models are registered
      on Base.metadata before create_all runs.
    """
    # Import your models to register them on the Base.metadata
    from app.core import models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(models.Base.metadata.create_all)


# ---------------------------
# Required for app/main.py
# ---------------------------

def get_engine() -> AsyncEngine:
    """
    Returns the SQLAlchemy async engine instance.
    Added to fix the ImportError in app/main.py.
    """
    return engine


# ---------------------------
# Optional: simple health checker (non-FastAPI)
# ---------------------------

async def check_db_connection() -> bool:
    """
    Try connecting to the DB. Returns True on success, False on failure.
    Useful for diagnostics or custom health endpoints.
    """
    try:
        async with engine.begin() as conn:
            await conn.run_sync(lambda sync_conn: None)
        return True
    except Exception:
        return False
