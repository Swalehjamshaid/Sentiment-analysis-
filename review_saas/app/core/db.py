# filename: app/core/db.py
import os
import logging
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker, AsyncEngine
from sqlalchemy.orm import declarative_base

# Setup logging to see the "Handshake" in the Railway logs
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app.core.db")

# --- 1. THE URL ALIGNMENT (CRITICAL) ---
# This ensures that both 'postgres://' and 'postgresql://' are 
# converted to the required 'postgresql+asyncpg://' for Async SQLAlchemy.
DATABASE_URL = os.getenv("DATABASE_URL", "")

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)
elif DATABASE_URL.startswith("postgresql://") and "+asyncpg" not in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

# --- 2. THE ENGINE ALIGNMENT ---
# Includes a 30-second timeout to prevent the 'asyncio runner' crash during startup.
engine: AsyncEngine = create_async_engine(
    DATABASE_URL,
    echo=False,           # Set to True for debugging SQL queries
    future=True,
    pool_pre_ping=True,    # Checks if connection is alive before using it
    connect_args={
        "command_timeout": 30
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
# This is the "Registry" that your models.py MUST import.
Base = declarative_base()

# --- 5. THE INITIALIZATION FUNCTION (100% ALIGNED) ---
async def init_models():
    """Safely creates tables on startup."""
    try:
        # ✅ THE IMPORT FIX: We import models INSIDE to stop circular import loops.
        # Based on your structure: review_saas / app / core / models.py
        from app.core import models 
        
        async with engine.begin() as conn:
            # 🚨 THE METADATA FIX: Use models.Base.metadata to ensure 
            # all tables (User, Reviews, etc.) are physically created.
            await conn.run_sync(models.Base.metadata.create_all)
            
        logger.info("✅ Database alignment complete: All tables created.")
    except Exception as e:
        logger.error(f"❌ Database alignment failed: {str(e)}")

# --- 6. DEPENDENCY FOR ROUTES ---
async def get_db():
    """Fastapi Dependency for providing DB sessions to routes."""
    async with SessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
