# filename: review_saas/app/core/db.py
import os
import logging
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker, AsyncEngine
from sqlalchemy.orm import declarative_base

# Setup logging for Railway deployment monitoring
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app.core.db")

# --- 1. THE URL ALIGNMENT ---
# This ensures both 'postgres://' and 'postgresql://' are 
# converted to the required 'postgresql+asyncpg://' driver.
DATABASE_URL = os.getenv("DATABASE_URL", "")

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)
elif DATABASE_URL.startswith("postgresql://") and "+asyncpg" not in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

# --- 2. THE ENGINE ALIGNMENT ---
# Includes a 60s timeout to prevent the 'asyncio runner' crash during slow DB wakes.
engine: AsyncEngine = create_async_engine(
    DATABASE_URL,
    echo=False,
    future=True,
    pool_pre_ping=True,
    connect_args={
        "command_timeout": 60 
    }
)

# --- 3. THE SESSION ALIGNMENT ---
SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False
)

# --- 4. THE BASE ALIGNMENT ---
# Every model in models.py MUST import this specific Base.
Base = declarative_base()

# --- 5. THE INITIALIZATION FUNCTION (PERMANENT FIX) ---
async def init_models():
    """Safely creates tables. Uses local import to break the circular deadlock."""
    try:
        # ✅ THE FIX: We import models INSIDE the function to stop the 'importlib' lock.
        from app.core import models 
        
        async with engine.begin() as conn:
            # Use models.Base.metadata to ensure all models are physically registered.
            await conn.run_sync(models.Base.metadata.create_all)
        logger.info("✅ Database alignment complete: Tables created.")
    except Exception as e:
        logger.error(f"❌ Database alignment failed: {str(e)}")

# --- 6. DEPENDENCY FOR ROUTES ---
async def get_db():
    """FastAPI Dependency for providing DB sessions to routes."""
    async with SessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
