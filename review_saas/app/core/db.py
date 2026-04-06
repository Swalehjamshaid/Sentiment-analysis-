# filename: app/core/db.py

import os
import logging
import hashlib
import json
import re

from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    async_sessionmaker,
)
from sqlalchemy.orm import declarative_base
from sqlalchemy.exc import ArgumentError

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
# DATABASE URL (PLACEHOLDER AWARE)
# -------------------------------
RAW_DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

if not RAW_DATABASE_URL:
    raise RuntimeError("❌ DATABASE_URL is not set")

def _resolve_placeholders(url: str) -> str:
    """
    Resolves patterns like:
    ${{Postgres.PGPASSWORD}}
    by mapping them to real env vars provided by Railway.
    """

    replacements = {
        "Postgres.PGPASSWORD": os.getenv("PGPASSWORD") or os.getenv("POSTGRES_PASSWORD"),
        "Postgres.PGDATABASE": os.getenv("PGDATABASE") or os.getenv("POSTGRES_DB"),
        "Postgres.RAILWAY_PRIVATE_DOMAIN": os.getenv("RAILWAY_PRIVATE_DOMAIN") or os.getenv("POSTGRES_HOST"),
    }

    for key, value in replacements.items():
        if value:
            url = url.replace(f"${{{{{key}}}}}", value)

    return url

DATABASE_URL = _resolve_placeholders(RAW_DATABASE_URL)

# Normalize postgres scheme
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace(
        "postgres://", "postgresql+asyncpg://", 1
    )

# Final safety check
if "${{" in DATABASE_URL or "}}" in DATABASE_URL:
    raise RuntimeError(
        f"❌ DATABASE_URL still contains unresolved placeholders:\n{DATABASE_URL}"
    )

logger.info("✅ DATABASE_URL resolved successfully")

# -------------------------------
# ENGINE & SESSION
# -------------------------------
try:
    engine = create_async_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        future=True,
    )
except ArgumentError as e:
    raise RuntimeError(f"❌ Invalid DATABASE_URL: {DATABASE_URL}") from e

SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# -------------------------------
# SCHEMA HASH SUPPORT
# -------------------------------
_SCHEMA_HASH_FILE = "/tmp/schema.hash"

async def compute_schema_hash():
    import app.core.models as models
    tables = sorted(models.Base.metadata.tables.keys())
    return hashlib.sha256(json.dumps(tables).encode()).hexdigest()

async def init_models():
    """Rebuild tables if schema changes (safe, deterministic)"""
    import app.core.models as models

    async with engine.begin() as conn:
        current_hash = await compute_schema_hash()
        previous_hash = None

        if os.path.exists(_SCHEMA_HASH_FILE):
            with open(_SCHEMA_HASH_FILE, "r") as f:
                previous_hash = f.read().strip()

        if current_hash != previous_hash:
            await conn.run_sync(models.Base.metadata.drop_all)
            await conn.run_sync(models.Base.metadata.create_all)
            with open(_SCHEMA_HASH_FILE, "w") as f:
                f.write(current_hash)
            logger.warning("⚠️ Database schema rebuilt")
        else:
            logger.info("✅ Database schema unchanged")

# -------------------------------
# SESSION DEPENDENCIES
# -------------------------------
async def get_db():
    async with SessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

# ✅ Compatibility alias (DO NOT REMOVE)
get_session = get_db
