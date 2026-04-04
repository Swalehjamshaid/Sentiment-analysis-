# filename: app/core/db.py
from __future__ import annotations

import os
import logging
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine, AsyncEngine
from sqlalchemy.orm import DeclarativeBase

# ------------------------------------------------------------------------------
# 1. SHARED DECLARATIVE BASE
# ------------------------------------------------------------------------------
# This MUST be defined here so that app/core/models.py can import it without 
# requiring the rest of the DB logic to be initialized first.
class Base(DeclarativeBase):
    """Declarative base for all SQLAlchemy models in the Review Intel AI system."""
    pass

# ------------------------------------------------------------------------------
# 2. DATABASE URL NORMALIZATION
# ------------------------------------------------------------------------------
def _get_db_url() -> str:
    """
    Retrieves and normalizes the DATABASE_URL from environment variables.
    Handles Postgres normalization for the asyncpg driver.
    """
    url = os.getenv("DATABASE_URL")
    if not url:
        # Local development fallback
        return "sqlite+aiosqlite:///./test.db"
    
    url = url.strip()
    # Railway/Heroku often provide 'postgres://', which asyncpg doesn't support directly
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql://") and "+asyncpg" not in url:
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    
    return url

DATABASE_URL: str = _get_db_url()

# ------------------------------------------------------------------------------
# 3. ASYNC ENGINE & SESSION FACTORY
# ------------------------------------------------------------------------------
# Optimized for production workloads with pooling settings
engine: AsyncEngine = create_async_engine(
    DATABASE_URL,
    echo=os.getenv("DEBUG", "false").lower() in {"1", "true", "yes"},
    future=True,
    pool_size=int(os.getenv("DB_POOL_SIZE", "10")),
    max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "20")),
)

# Factory for creating AsyncSession instances
SessionLocal = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession,
)

# ------------------------------------------------------------------------------
# 4. EXPORTED UTILITIES & FASTAPI DEPENDENCIES
# ------------------------------------------------------------------------------

def get_engine() -> AsyncEngine:
    """
    Returns the global async engine instance.
    Required by app/main.py for lifespan metadata management.
    """
    return engine

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that yields an AsyncSession.
    Usage: db: AsyncSession = Depends(get_db)
    """
    async with SessionLocal() as session:
        try:
            yield session
        finally:
            # Context manager handles closing, but explicit close is added for safety
            await session.close()

# ------------------------------------------------------------------------------
# 5. INITIALIZATION HELPER (The Fix for Circular Imports)
# ------------------------------------------------------------------------------

async def init_models() -> None:
    """
    Creates all database tables based on the models defined in app.core.models.
    
    CRITICAL: The 'models' import is local to this function. This prevents
    the 'runner.run(main)' and 'importlib' errors caused by circular dependencies.
    """
    # Local import ensures Base.metadata is fully populated before create_all runs
    from app.core import models 

    logging.info(f"🛠️ Initializing database tables for Schema Version: {models.SCHEMA_VERSION}")
    
    async with engine.begin() as conn:
        # This will create 'users', 'companies', 'reviews', 'company_cids', etc.
        await conn.run_sync(Base.metadata.create_all)
    
    logging.info("✅ Database tables synchronized successfully.")

# ------------------------------------------------------------------------------
# 6. DIAGNOSTIC HEALTH CHECK
# ------------------------------------------------------------------------------

async def check_db_connection() -> bool:
    """Diagnostic helper to verify DB connectivity on startup."""
    try:
        async with engine.begin() as conn:
            await conn.run_sync(lambda sync_conn: None)
        return True
    except Exception as e:
        logging.error(f"❌ Database connection check failed: {e}")
        return False
