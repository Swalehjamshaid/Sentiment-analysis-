# filename: app/core/db.py
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
import os

class Base(DeclarativeBase):
    pass  # Models will import this

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./test.db").replace("postgres://", "postgresql+asyncpg://")
engine = create_async_engine(DATABASE_URL, future=True)
SessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

async def get_session():
    async with SessionLocal() as session:
        yield session

async def init_models():
    # CRITICAL: Import models ONLY inside this function to break the loop
    from app.core import models 
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
