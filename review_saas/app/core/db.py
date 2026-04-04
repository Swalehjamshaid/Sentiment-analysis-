# filename: app/core/db.py

import os
import logging
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    create_async_engine,
)
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.engine import URL
from sqlalchemy.exc import SQLAlchemyError

from app.core import models

logger = logging.getLogger("app.core.db")

# --------------------------- DATABASE URL ---------------------------
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:password@localhost:5432/reviewsaaS",
)

# --------------------------- Async Engine ---------------------------
try:
    engine: AsyncEngine = create_async_engine(
        DATABASE_URL,
        echo=False,  # Set True for debug SQL logging
        future=True,
    )
    logger.info("✅ Async SQLAlchemy Engine created successfully")
except SQLAlchemyError as e:
    logger.error(f"❌ Error creating AsyncEngine: {e}")
    raise e

# --------------------------- Session Local ---------------------------
SessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# --------------------------- Base ---------------------------
Base = models.Base

# --------------------------- DB Utilities ---------------------------
async def init_models():
    """
    Initialize all models (create tables if they don't exist)
    """
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("✅ Database tables created successfully")
    except SQLAlchemyError as e:
        logger.error(f"❌ Failed to create database tables: {e}")
        raise e

async def drop_models():
    """
    Drop all models (useful for schema reset)
    """
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        logger.warning("🧨 Dropped all database tables")
    except SQLAlchemyError as e:
        logger.error(f"❌ Failed to drop database tables: {e}")
        raise e

# --------------------------- Dependency ---------------------------
async def get_session() -> AsyncSession:
    """
    Async DB session dependency for FastAPI
    """
    async with SessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
