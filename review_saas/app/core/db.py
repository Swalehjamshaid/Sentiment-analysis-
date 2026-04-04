# filename: app/core/db.py
from __future__ import annotations

import os
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine, AsyncEngine
from sqlalchemy.orm import DeclarativeBase

# ------------------------------------------------------------------------------
# 1. Declarative Base
# ------------------------------------------------------------------------------
# We define Base here. app/core/models.py must import this: 
# from app.core.db import Base
class Base(DeclarativeBase):
    """Declarative base for SQLAlchemy models."""
    pass

# ------------------------------------------------------------------------------
# 2. Configuration & URL Handling
# ------------------------------------------------------------------------------

def _get_env(key: str, default: str | None = None) -> str:
    value = os.getenv(key, default)
    if value is None or not str(value).strip():
        # Fallback for local testing if env is missing
        if key == "DATABASE_URL":
            return "sqlite+aiosqlite:///./test.db"
        raise RuntimeError(f"Missing required environment variable: {key}")
    return str(value)

def _normalize_db_url(url: str) -> str:
    """
    Ensure async dialect is used.
    - postgres:// -> postgresql+asyncpg://
    - postgresql:// -> postgresql+asyncpg://
    """
    url = url.strip()
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    if url.startswith("postgresql://") and "+asyncpg" not in url:
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url

DATABASE_URL: str = _normalize_db_url(_get_env("DATABASE_URL"))

# ------------------------------------------------------------------------------
# 3. Engine & Session Setup
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
# 4. Utilities & Dependencies
# ------------------------------------------------------------------------------

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that yields an AsyncSession.
    Used in routes like: db: AsyncSession = Depends(get_db)
    """
    async with SessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

def get_engine() -> AsyncEngine:
    """
    Returns the SQLAlchemy async engine instance.
    Required for app/main.py lifespan management.
    """
    return engine

# ------------------------------------------------------------------------------
# 5. Initialization Helper
# ------------------------------------------------------------------------------

async def init_models() -> None:
    """
    Create tables from SQLAlchemy models.
    Importing models INSIDE the function prevents Circular Import errors.
    """
    # Local import to prevent circular dependency
    from app.core import models 

    async with engine.begin() as conn:
        # Create all tables registered on Base.metadata
        await conn.run_sync(Base.metadata.create_all)

# ------------------------------------------------------------------------------
# 6. Health Check
# ------------------------------------------------------------------------------

async def check_db_connection() -> bool:
    """Diagnostic helper to verify DB connectivity."""
    try:
        async with engine.begin() as conn:
            await conn.run_sync(lambda sync_conn: None)
        return True
    except Exception:
        return False
