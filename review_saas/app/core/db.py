# filename: app/core/db.py
import os
import logging
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker, AsyncEngine
from sqlalchemy.orm import declarative_base

# Setup logging to see what's happening during the Railway boot
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 1. THE URL ALIGNMENT
# Railway often gives "postgres://", but Async SQLAlchemy NEEDS "postgresql+asyncpg://"
DATABASE_URL = os.getenv("DATABASE_URL", "")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)

# 2. THE ENGINE
# We add a 30-second timeout so the 'asyncio runner' doesn't crash if the DB is slow.
engine: AsyncEngine = create_async_engine(
    DATABASE_URL,
    echo=False,
    future=True,
    pool_pre_ping=True,
    connect_args={
        "command_timeout": 30
    }
)

# 3. THE SESSION
SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False
)

# 4. THE BASE
# This is the "Parent" for all your models.
Base = declarative_base()

# 5. THE INITIALIZATION FUNCTION
async def init_models():
    """Safely creates tables on startup."""
    try:
        # ✅ CRITICAL: We import models INSIDE the function.
        # This stops the 'frozen importlib' error (Circular Import).
        from app.core import models 
        
        async with engine.begin() as conn:
            # This line physically creates the tables in Postgres
            await conn.run_sync(Base.metadata.create_all)
        logger.info("✅ Database alignment complete: Tables created.")
    except Exception as e:
        logger.error(f"❌ Database alignment failed: {e}")
