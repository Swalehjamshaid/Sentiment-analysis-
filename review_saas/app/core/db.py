# filename: app/core/db.py

import os
import logging
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base

# -------------------------------
# LOGGING
# -------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app.core.db")

# -------------------------------
# BASE (DO NOT CHANGE)
# -------------------------------
Base = declarative_base()

# -------------------------------
# DATABASE URL FIX (SAFE)
# -------------------------------
DATABASE_URL = os.getenv("DATABASE_URL", "")

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)

elif DATABASE_URL.startswith("postgresql://") and "+asyncpg" not in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

# -------------------------------
# ENGINE (SAFE INIT)
# -------------------------------
engine = create_async_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    future=True
)

# -------------------------------
# SESSION FACTORY
# -------------------------------
SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)

# -------------------------------
# INIT MODELS (NO CHANGE IN BEHAVIOR)
# -------------------------------
async def init_models():
    """Initialize DB safely without import deadlock"""
    try:
        import app.core.models as models  # delayed import

        async with engine.begin() as conn:
            await conn.run_sync(models.Base.metadata.drop_all)
            await conn.run_sync(models.Base.metadata.create_all)

        logger.info("✅ Database Fresh Start: Tables rebuilt successfully.")

    except Exception as e:
        logger.error(f"❌ Database Handshake Failed: {e}")

# -------------------------------
# DEPENDENCY (NO CHANGE)
# -------------------------------
async def get_db():
    async with SessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

# -------------------------------
# 🔥 CRITICAL FIX (NO BREAKING CHANGE)
# -------------------------------
# This ensures compatibility with dashboard.py
get_session = get_db
