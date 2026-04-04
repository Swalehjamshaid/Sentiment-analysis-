# filename: app/core/db.py
from __future__ import annotations
import os
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine, AsyncEngine
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass

def _get_db_url() -> str:
    url = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./test.db").strip()
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql://") and "+asyncpg" not in url:
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url

DATABASE_URL = _get_db_url()
engine = create_async_engine(DATABASE_URL, future=True)
SessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)

def get_session(): # For router dependency
    return SessionLocal()

async def init_models():
    from app.core import models 
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
