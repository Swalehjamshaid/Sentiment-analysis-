# filename: app/core/db.py
import os
import logging
import asyncio
import hashlib
import json

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base

# -------------------------------
# LOGGING
# -------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app.core.db")

# -------------------------------
# BASE
# -------------------------------
Base = declarative_base()

# -------------------------------
# DATABASE URL FIX
# -------------------------------
DATABASE_URL = os.getenv("DATABASE_URL", "")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)
elif DATABASE_URL.startswith("postgresql://") and "+asyncpg" not in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

# -------------------------------
# ENGINE & SESSION
# -------------------------------
engine = create_async_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    future=True
)
SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)

# -------------------------------
# SCHEMA HASH FILE
# -------------------------------
_schema_hash_file = "/tmp/schema.hash"

async def compute_schema_hash():
    import app.core.models as models
    tables = sorted(models.Base.metadata.tables.keys())
    return hashlib.sha256(json.dumps(tables).encode()).hexdigest()

async def init_models():
    """Rebuild tables if schema changed"""
    import app.core.models as models
    async with engine.begin() as conn:
        current_hash = await compute_schema_hash()
        previous_hash = None
        if os.path.exists(_schema_hash_file):
            with open(_schema_hash_file, "r") as f:
                previous_hash = f.read().strip()
        if current_hash != previous_hash:
            await conn.run_sync(models.Base.metadata.drop_all)
            await conn.run_sync(models.Base.metadata.create_all)
            with open(_schema_hash_file, "w") as f:
                f.write(current_hash)
            logger.info("✅ Database rebuilt due to schema change")
        else:
            logger.info("✅ Schema unchanged: tables intact")

async def get_db():
    async with SessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
