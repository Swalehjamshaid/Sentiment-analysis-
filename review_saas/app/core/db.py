# filename: app/core/db.py

import os
import logging
import hashlib
import json

from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    async_sessionmaker,
)
from sqlalchemy.exc import ArgumentError
from sqlalchemy import text

from app.core.base import Base

# -------------------------------
# LOGGING
# -------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app.core.db")

# -------------------------------
# DATABASE URL (UNCHANGED ENV)
# -------------------------------
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL not set")

# -------------------------------
# ENGINE
# -------------------------------
engine = create_async_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    future=True,
)

SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# -------------------------------
# SCHEMA VERSIONING RULE
# -------------------------------
_SCHEMA_FILE = "/tmp/schema_version.hash"

async def compute_schema_hash() -> str:
    import app.core.models as models

    meta = models.Base.metadata
    payload = {
        table: sorted(col.name for col in meta.tables[table].columns)
        for table in meta.tables
    }

    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:12]


async def init_models():
    """
    ✅ SCHEMA RULE:
    - Every schema change creates a NEW PostgreSQL schema
    - No tables are dropped
    - Old data always preserved
    """

    import app.core.models as models

    schema_hash = await compute_schema_hash()
    schema_name = f"app_schema_{schema_hash}"

    async with engine.begin() as conn:
        await conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}"'))
        await conn.execute(text(f'SET search_path TO "{schema_name}"'))

        await conn.run_sync(
            lambda sync_conn: models.Base.metadata.create_all(
                bind=sync_conn, checkfirst=True
            )
        )

        with open(_SCHEMA_FILE, "w") as f:
            f.write(schema_name)

        logger.warning(f"🧬 Active DB schema: {schema_name}")

# -------------------------------
# SESSION DEPENDENCIES
# -------------------------------
async def get_db():
    async with SessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

# Backward compatibility
get_session = get_db
