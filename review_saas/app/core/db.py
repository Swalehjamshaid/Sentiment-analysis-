# filename: app/core/db.py
from __future__ import annotations
import os
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine, AsyncEngine
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass

def _get_db_url() -> str:
    # Use the Railway DATABASE_URL or fallback to local sqlite
    url = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./test.db").strip()
    # Ensure the driver is async-compatible
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql://") and "+asyncpg" not in url:
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url

DATABASE_URL = _get_db_url()

# Engine creation with pool_pre_ping to keep connections alive on Railway
engine: AsyncEngine = create_async_engine(
    DATABASE_URL, 
    future=True, 
    pool_pre_ping=True
)

SessionLocal = async_sessionmaker(
    bind=engine, 
    expire_on_commit=False, 
    class_=AsyncSession
)

async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

async def init_models():
    # Local import inside the function to break circular dependency
    from app.core import models 
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
