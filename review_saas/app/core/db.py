# filename: app/core/db.py
import os
import logging
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app.core.db")

# 1. THE BASE (MUST BE DEFINED HERE TO BREAK THE CIRCLE)
Base = declarative_base()

# 2. THE URL REPAIR
DATABASE_URL = os.getenv("DATABASE_URL", "")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)
elif DATABASE_URL.startswith("postgresql://") and "+asyncpg" not in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

# 3. ENGINE & SESSION
engine = create_async_engine(
    DATABASE_URL, 
    pool_pre_ping=True,
    future=True
)
SessionLocal = async_sessionmaker(
    bind=engine, 
    class_=AsyncSession, 
    expire_on_commit=False
)

# 4. THE LOADER (LOCAL IMPORT ONLY)
async def init_models():
    """Wakes up the models only when the DB is ready to avoid import deadlocks."""
    try:
        # ✅ DELAYED IMPORT: Physically prevents the loader from locking
        import app.core.models as models 
        async with engine.begin() as conn:
            # Drop/Create for the Fresh Start
            await conn.run_sync(models.Base.metadata.drop_all)
            await conn.run_sync(models.Base.metadata.create_all)
        logger.info("✅ Database Fresh Start: Tables rebuilt successfully.")
    except Exception as e:
        logger.error(f"❌ Database Handshake Failed: {e}")

async def get_db():
    async with SessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
