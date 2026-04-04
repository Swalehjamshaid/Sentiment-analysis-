# filename: app/core/db.py
from __future__ import annotations
import os
import logging
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine, AsyncEngine
from sqlalchemy.orm import DeclarativeBase

# Setup logger for DB specific issues
logger = logging.getLogger("app.db")

class Base(DeclarativeBase):
    pass

def _get_db_url() -> str:
    url = os.getenv("DATABASE_URL")
    if not url:
        return "sqlite+aiosqlite:///./test.db"
    
    url = url.strip()
    # Fix for Railway/Heroku postgres strings
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql://") and "+asyncpg" not in url:
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url

DATABASE_URL: str = _get_db_url()

# Extra safety: Ensure we use the right engine parameters for SQLite vs Postgres
connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

try:
    engine: AsyncEngine = create_async_engine(
        DATABASE_URL,
        echo=os.getenv("DEBUG", "false").lower() in {"1", "true", "yes"},
        future=True,
        # Only use pooling for Postgres
        **({"pool_size": 10, "max_overflow": 20} if not DATABASE_URL.startswith("sqlite") else {})
    )

    SessionLocal = async_sessionmaker(
        bind=engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )
except Exception as e:
    logger.error(f"❌ Failed to create SQLAlchemy engine: {e}")
    raise

def get_engine() -> AsyncEngine:
    return engine

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

async def init_models() -> None:
    try:
        from app.core import models 
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info(f"✅ DB Tables synced. Schema Version: {getattr(models, 'SCHEMA_VERSION', 'unknown')}")
    except Exception as e:
        logger.error(f"❌ Table Initialization Error: {e}")
        raise
