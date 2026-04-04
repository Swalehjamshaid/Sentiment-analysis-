# filename: app/core/db.py

import os
import logging
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    create_async_engine,
)
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger("app.core.db")

# --------------------------- Base (SOURCE OF TRUTH) ---------------------------
Base = declarative_base()

# --------------------------- DATABASE URL ---------------------------
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:password@localhost:5432/reviewsaaS",
)

# --------------------------- Async Engine ---------------------------
try:
    engine: AsyncEngine = create_async_engine(
        DATABASE_URL,
        echo=False,      # Set True for SQL debugging
        future=True,     # SQLAlchemy 2.x behavior
    )
    logger.info("✅ Async SQLAlchemy Engine created successfully")
except SQLAlchemyError as e:
    logger.error(f"❌ Error creating AsyncEngine: {e}")
    raise

# --------------------------- Session Factory ---------------------------
SessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# --------------------------- DB Utilities ---------------------------
async def init_models() -> None:
    """Create all tables (safe, non-destructive)"""
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("✅ Database tables created successfully")
    except SQLAlchemyError as e:
        logger.error(f"❌ Failed to create database tables: {e}")
        raise


async def drop_models() -> None:
    """Drop all tables (use only for dev/reset)"""
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        logger.warning("🧨 Dropped all database tables")
    except SQLAlchemyError as e:
        logger.error(f"❌ Failed to drop database tables: {e}")
        raise

# --------------------------- Dependency ---------------------------
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session
