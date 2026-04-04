import os
import logging
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker, AsyncEngine
from sqlalchemy.orm import DeclarativeBase

# Setup logging for database operations
logger = logging.getLogger("app.core.db")

class Base(DeclarativeBase):
    """
    Shared Declarative Base. 
    Models will import this to avoid circular dependencies with engine/session logic.
    """
    pass

def _get_db_url() -> str:
    """Normalizes the DATABASE_URL for asyncpg compatibility."""
    url = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./test.db").strip()
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql://") and "+asyncpg" not in url:
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url

DATABASE_URL = _get_db_url()

# Engine configuration with pool_pre_ping for Railway stability
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
    """Dependency for FastAPI routes to provide a database session."""
    async with SessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

async def init_models() -> None:
    """
    Initializes database tables.
    CRITICAL: Models are imported LOCALLY inside this function to prevent 
    the 'frozen importlib' circular dependency crash at runtime.
    """
    try:
        from app.core import models 
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("✅ Database tables initialized successfully.")
    except Exception as e:
        logger.error(f"❌ Failed to initialize database tables: {e}")
        raise e
