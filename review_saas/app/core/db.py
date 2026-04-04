# filename: review_saas/app/core/db.py
import os
import logging
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker, AsyncEngine
from sqlalchemy.orm import declarative_base

# Setup logging for Railway deployment monitoring
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app.core.db")

# --- 1. THE URL ALIGNMENT ---
DATABASE_URL = os.getenv("DATABASE_URL", "")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)
elif DATABASE_URL.startswith("postgresql://") and "+asyncpg" not in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

# --- 2. THE ENGINE ---
engine: AsyncEngine = create_async_engine(
    DATABASE_URL,
    echo=False,
    future=True,
    pool_pre_ping=True,
    connect_args={"command_timeout": 30}
)

# --- 3. THE SESSION ---
SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False
)

# --- 4. THE BASE ---
# Level 1 Registry: All models must import THIS Base.
Base = declarative_base()

# --- 5. THE INITIALIZATION (THE LOOP BREAKER) ---
async def init_models():
    """Safely creates tables. Uses local import to break the vicious circle."""
    try:
        # ✅ CRITICAL: This import MUST stay inside the function 
        # to prevent the 'importlib' deadlock.
        from app.core import models 
        
        async with engine.begin() as conn:
            # We use models.Base to ensure all tables are registered
            await conn.run_sync(models.Base.metadata.create_all)
        logger.info("✅ Database alignment complete: Tables created.")
    except Exception as e:
        logger.error(f"❌ Database alignment failed: {str(e)}")

# --- 6. DEPENDENCY ---
async def get_db():
    async with SessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
