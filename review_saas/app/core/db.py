# filename: app/core/db.py
from __future__ import annotations

import os
import logging
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession, 
    async_sessionmaker, 
    create_async_engine, 
    AsyncEngine
)
from sqlalchemy.orm import DeclarativeBase

# --------------------------- Logging ---------------------------
logger = logging.getLogger("app.db")

# --------------------------- 1. SHARED BASE ---------------------------
# Defined here so models.py can import it without importing the engine logic,
# which breaks circular dependency loops.
class Base(DeclarativeBase):
    """Declarative base for all SQLAlchemy models."""
    pass

# --------------------------- 2. DATABASE URL ---------------------------
def _get_db_url() -> str:
    """
    Normalizes the DATABASE_URL. 
    Converts 'postgres://' to 'postgresql+asyncpg://' for SQLAlchemy 2.0 compatibility.
    """
    url = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./test.db").strip()
    
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql://") and "+asyncpg" not in url:
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        
    return url

DATABASE_URL: str = _get_db_url()

# --------------------------- 3. ENGINE & SESSION ---------------------------
# Using pool_pre_ping=True to handle Railway's database connection recycling.
engine: AsyncEngine = create_async_engine(
    DATABASE_URL,
    echo=os.getenv("DEBUG", "false").lower() in {"1", "true", "yes"},
    future=True,
    pool_pre_ping=True,
    connect_args={"command_timeout": 60} if "postgresql" in DATABASE_URL else {}
)

SessionLocal = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession,
)

# --------------------------- 4. DEPENDENCIES ---------------------------
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI Dependency for database sessions used in routes."""
    async with SessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

# Alias for main.py alignment
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Alias for get_session to match FastAPI standard naming."""
    async with SessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

# --------------------------- 5. INITIALIZATION ---------------------------
async def init_models() -> None:
    """
    Initializes database tables.
    CRITICAL: The import of 'models' is kept inside this function. 
    This prevents the 'frozen importlib' error by ensuring models are only 
    loaded AFTER the Base and Engine are ready.
    """
    try:
        from app.core import models 
        async with engine.begin() as conn:
            # metadata.create_all is a synchronous call wrapped in run_sync for async engines
            await conn.run_sync(Base.metadata.create_all)
        logger.info("✅ Database tables synchronized successfully.")
    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}")
        raise e
