# filename: app/core/db.py
import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base

# The Base must be defined here, NOT in models.py
Base = declarative_base()

DATABASE_URL = os.getenv("DATABASE_URL", "").replace("postgres://", "postgresql+asyncpg://", 1)

engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

async def get_db():
    async with SessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

async def init_models():
    """This function 'wakes up' the models only when the DB is ready."""
    import app.core.models as models # <--- Local import
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
