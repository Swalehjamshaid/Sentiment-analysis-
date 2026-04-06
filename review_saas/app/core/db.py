# filename: app/core/db.py

import os
import logging
import hashlib
import json
from typing import Optional

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
# DATABASE URL (RAILWAY PLACEHOLDER SAFE)
# -------------------------------
RAW_DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

if not RAW_DATABASE_URL:
    raise RuntimeError("❌ DATABASE_URL environment variable is missing")

def _resolve_railway_placeholders(url: str) -> str:
    """
    Resolves Railway-style placeholders inside DATABASE_URL.
    Works without changing environment variables.
    """

    replacements = {
        "Postgres.PGPASSWORD": (
            os.getenv("PGPASSWORD")
            or os.getenv("POSTGRES_PASSWORD")
        ),
        "Postgres.PGDATABASE": (
            os.getenv("PGDATABASE")
            or os.getenv("POSTGRES_DB")
        ),
        "Postgres.RAILWAY_PRIVATE_DOMAIN": (
            os.getenv("RAILWAY_PRIVATE_DOMAIN")
            or os.getenv("POSTGRES_HOST")
        ),
    }

    resolved_url = url
    for key, value in replacements.items():
        if value:
            resolved_url = resolved_url.replace(f"${{{{{key}}}}}", value)

    return resolved_url

DATABASE_URL = _resolve_railway_placeholders(RAW_DATABASE_URL)

# Normalize postgres scheme for asyncpg
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace(
        "postgres://", "postgresql+asyncpg://", 1
    )
elif DATABASE_URL.startswith("postgresql://") and "+asyncpg" not in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace(
        "postgresql://", "postgresql+asyncpg://", 1
    )

# Final validation
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
except ArgumentError as exc:
    raise RuntimeError(
        f"❌ Invalid DATABASE_URL after resolution:\n{DATABASE_URL}"
    ) from exc

SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# -------------------------------
# SCHEMA HASH MANAGEMENT
# -------------------------------
_SCHEMA_HASH_FILE = "/tmp/schema.hash"

async def compute_schema_hash() -> str:
    import app.core.models as models
    tables = sorted(models.Base.metadata.tables.keys())
    return hashlib.sha256(json.dumps(tables).encode()).hexdigest()

async def init_models():
    """
    Rebuild tables only when schema changes.
    Deterministic and startup-safe.
    """
    import app.core.models as models

    async with engine.begin() as conn:
        current_hash = await compute_schema_hash()
        previous_hash: Optional[str] = None

        if os.path.exists(_SCHEMA_HASH_FILE):
            with open(_SCHEMA_HASH_FILE, "r") as f:
                previous_hash = f.read().strip()

        if current_hash != previous_hash:
            await conn.run_sync(models.Base.metadata.drop_all)
            await conn.run_sync(models.Base.metadata.create_all)
            with open(_SCHEMA_HASH_FILE, "w") as f:
                f.write(current_hash)
            logger.warning("⚠️ Database schema rebuilt (change detected)")
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

# ✅ BACKWARD-COMPATIBLE ALIAS (DO NOT REMOVE)
# Required by routes using Depends(get_session)
get_session = get_db
