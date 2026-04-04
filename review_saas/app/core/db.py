# filename: app/core/db.py
import os
import logging
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker, AsyncEngine
from sqlalchemy.orm import DeclarativeBase

logger = logging.getLogger("app.core.db")

class Base(DeclarativeBase):
    """
    Isolated Declarative Base.
    Defining this here stops the circular loop that often causes 
    uvicorn/importer.py to fail during the string resolution phase.
    """
    pass

def _get_db_url() -> str:
    url = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./test.db").strip()
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql://") and "+asyncpg" not in url:
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url

DATABASE_URL = _get_db_url()

engine: AsyncEngine = create_async_engine(
    DATABASE_URL,
    echo=False,
    future=True,
    pool_pre_ping=True
)

SessionLocal = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession,
)

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

async def init_models() -> None:
    """
    Initializes database tables.
    Uses a local import to break the vicious circle for good.
    """
    try:
        import app.core.models 
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("✅ Database schema initialized.")
    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}")
        raise e
