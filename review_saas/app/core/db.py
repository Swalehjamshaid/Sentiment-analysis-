# filename: review_saas/app/core/db.py
import os
import logging
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker, AsyncEngine
from sqlalchemy.orm import declarative_base

# --------------------------
# Logging
# --------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app.core.db")

# --------------------------
# DATABASE URL
# --------------------------
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is not set!")

# Normalize for asyncpg
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)
elif DATABASE_URL.startswith("postgresql://") and "+asyncpg" not in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

# --------------------------
# ASYNC ENGINE
# --------------------------
engine: AsyncEngine = create_async_engine(
    DATABASE_URL,
    echo=False,
    future=True,
    pool_pre_ping=True,
    connect_args={"timeout": 30, "command_timeout": 30}
)

# --------------------------
# SESSION MAKER
# --------------------------
SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False
)

# --------------------------
# BASE
# --------------------------
Base = declarative_base()

# --------------------------
# INIT MODELS
# --------------------------
async def init_models():
    """
    Create all tables safely at startup.
    Import models locally to avoid circular imports.
    """
    try:
        from app.core import models  # models must inherit from Base defined above
        if not hasattr(models, "Base"):
            logger.warning("⚠️ models.Base not found. Make sure all models inherit from db.Base")
            return
        
        async with engine.begin() as conn:
            # Use the global Base so all tables are registered
            await conn.run_sync(Base.metadata.create_all)
        logger.info("✅ Database alignment complete: Tables created.")
    except Exception as e:
        logger.error(f"❌ Database alignment failed: {e}")
        raise  # Fail startup if DB alignment fails

# --------------------------
# FASTAPI DEPENDENCY
# --------------------------
async def get_db():
    async with SessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
