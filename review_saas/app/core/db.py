import os
import logging
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
    async_sessionmaker,
    AsyncEngine,
)
from sqlalchemy.orm import DeclarativeBase

# ---------------------------------------------------------
# LOGGING
# ---------------------------------------------------------
logger = logging.getLogger("app.core.db")

# ---------------------------------------------------------
# DECLARATIVE BASE (ISOLATED TO PREVENT CIRCULAR IMPORTS)
# ---------------------------------------------------------
class Base(DeclarativeBase):
    """
    Shared Declarative Base.
    Imported by models without triggering engine creation.
    """
    pass

# ---------------------------------------------------------
# DATABASE URL NORMALIZATION
# ---------------------------------------------------------
def _get_db_url() -> str:
    """
    Normalize DATABASE_URL for SQLAlchemy async usage.
    """
    url = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./test.db").strip()

    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql://") and "+asyncpg" not in url:
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)

    return url


DATABASE_URL = _get_db_url()

# ---------------------------------------------------------
# ASYNC DATABASE ENGINE
# ---------------------------------------------------------
engine_kwargs = {
    "echo": False,
    "future": True,
    "pool_pre_ping": True,
}

if DATABASE_URL.startswith("postgresql+asyncpg://"):
    engine_kwargs["connect_args"] = {"command_timeout": 60}

engine: AsyncEngine = create_async_engine(
    DATABASE_URL,
    **engine_kwargs,
)

# ---------------------------------------------------------
# SESSION FACTORY
# ---------------------------------------------------------
SessionLocal = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession,
)

# ---------------------------------------------------------
# FASTAPI DATABASE DEPENDENCY (PRIMARY)
# ---------------------------------------------------------
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Primary FastAPI dependency that yields an AsyncSession.
    """
    async with SessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

# ---------------------------------------------------------
# ✅ BACKWARD‑COMPATIBILITY ALIAS (CRITICAL FIX)
# ---------------------------------------------------------
# Existing route files expect `get_session`
# We intentionally map it to `get_db` to avoid touching routes
get_session = get_db

# ---------------------------------------------------------
# MODEL INITIALIZATION (SAFE)
# ---------------------------------------------------------
async def init_models() -> None:
    """
    Initialize database tables.
    Models are imported locally to avoid circular imports.
    """
    try:
        import app.core.models  # noqa: F401

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        logger.info("✅ Database schema initialized successfully.")

    except Exception:
        logger.exception("❌ Database initialization failed")
        raise
