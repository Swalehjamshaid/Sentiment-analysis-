import os
import logging
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker, AsyncEngine
from sqlalchemy.orm import DeclarativeBase

# Setup logging
logger = logging.getLogger("app.core.db")

class Base(DeclarativeBase):
    """
    Isolated Declarative Base.
    Defining this here allows models.py to import it without triggering 
    the engine or session logic, which is the root cause of circular loops.
    """
    pass

def _get_db_url() -> str:
    """Normalizes the DATABASE_URL for SQLAlchemy 2.0 async drivers."""
    url = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./test.db").strip()
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql://") and "+asyncpg" not in url:
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url

DATABASE_URL = _get_db_url()

# Engine configuration with pool_pre_ping for cloud stability (Railway/Render)
engine: AsyncEngine = create_async_engine(
    DATABASE_URL,
    echo=False,
    future=True,
    pool_pre_ping=True
)

# Async session factory
SessionLocal = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession,
)

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI Dependency for database sessions."""
    async with SessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

async def init_models() -> None:
    """
    Initializes database tables.
    CRITICAL: Models are imported LOCALLY inside this function to prevent 
    circular dependency crashes during the app boot sequence.
    """
    try:
        from app.core import models 
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("✅ Database schema initialized successfully.")
    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}")
        raise e
