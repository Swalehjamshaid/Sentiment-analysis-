# filename: review_saas/app/core/db.py
import os
import logging
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base

logger = logging.getLogger("app.core.db")
Base = declarative_base()

# --- Driver Repair ---
DATABASE_URL = os.getenv("DATABASE_URL", "").replace("postgres://", "postgresql+asyncpg://", 1)

engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

async def init_models():
    """The Circle Breaker: Delays model loading until the event loop is fully stable."""
    try:
        # Give the system one last breath
        await asyncio.sleep(1) 
        
        # ✅ THE ONLY WAY OUT: Absolute local import
        import app.core.models as models
        
        async with engine.begin() as conn:
            # Check if we can talk to the DB first
            from sqlalchemy import text
            await conn.execute(text("SELECT 1"))
            # Create tables
            await conn.run_sync(models.Base.metadata.create_all)
            
        logger.info("✅ Database alignment complete.")
    except Exception as e:
        logger.error(f"❌ Loader failed at _call_with_frames_removed: {e}")
