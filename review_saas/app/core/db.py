# ============================================================
# filename: app/core/db.py
# ============================================================

import os
import logging
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    create_async_engine,
    async_sessionmaker,
)
from sqlalchemy.orm import declarative_base
from sqlalchemy.exc import SQLAlchemyError

# ------------------------------------------------------------
# Logging
# ------------------------------------------------------------
logger = logging.getLogger("app.core.db")

# ------------------------------------------------------------
# Base (SINGLE SOURCE OF TRUTH)
# ------------------------------------------------------------
Base = declarative_base()

# ------------------------------------------------------------
# Database URL (MUST be async)
# ------------------------------------------------------------
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is not set")

# 🔐 HARD GUARD — prevents ALL past failures
if "+asyncpg" not in DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL must use async driver "
        "(example: postgresql+asyncpg://user:pass@host/db)"
    )

logger.info("✅ DATABASE_URL validated for async usage")

# ------------------------------------------------------------
# Async Engine (SQLAlchemy 2.x compliant)
# ------------------------------------------------------------
try:
    engine: AsyncEngine = create_async_engine(
        DATABASE_URL,
        echo=False,
        future=True,
    )
    logger.info("✅ Async SQLAlchemy engine created")
except SQLAlchemyError as exc:
    logger.exception("❌ Failed to create async engine")
    raise exc

# ------------------------------------------------------------
# Async Session Factory (2.x native)
# ------------------------------------------------------------
SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# ------------------------------------------------------------
# Dependency
# ------------------------------------------------------------
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session

# ------------------------------------------------------------
# Init Models (SAFE — no drops)
# ------------------------------------------------------------
async def init_models() -> None:
    """
    Create tables if they do not exist.
    NON‑DESTRUCTIVE.
    """
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("✅ Database tables verified / created")
    except SQLAlchemyError as exc:
        logger.exception("❌ Failed during init_models")
        raise exc

# ------------------------------------------------------------
# Drop Models (DEV‑ONLY)
# ------------------------------------------------------------
async def drop_models() -> None:
    """
    DROP ALL TABLES.
    ⚠️ Use ONLY in development/testing.
    """
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        logger.warning("🧨 All database tables dropped")
    except SQLAlchemyError as exc:
        logger.exception("❌ Failed during drop_models")
        raise exc
