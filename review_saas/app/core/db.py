# filename: app/core/db.py
import os
import logging
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    async_sessionmaker,
)
from sqlalchemy import text

# Assuming Base is in app.core.base
from app.core.base import Base

# -----------------------------------------------------------------------------
# ⭐ STEGMAN RULE: SCHEMA VERSIONING
# POINT OF CHANGE: Update this string here to trigger a total wipe/rebuild.
# This avoids the circular import crash with main.py.
# -----------------------------------------------------------------------------
CURRENT_SCHEMA_VERSION = "2026-04-06-V1II" 

# -------------------------------
# LOGGING
# -------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app.core.db")

# -------------------------------
# DATABASE URL (REPAIR FOR ASYNC)
# -------------------------------
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL not set")

# Fix for Railway/Postgres: SQLAlchemy needs 'postgresql+asyncpg'
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)

# -------------------------------
# ENGINE & SESSION
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

# -----------------------------------------------------------------------------
# ⭐ THE STEGMAN RULE: WIPE & REBUILD LOGIC
# -----------------------------------------------------------------------------
async def init_models():
    """
    ✅ UPDATED SCHEMA RULE:
    1. Uses the local CURRENT_SCHEMA_VERSION defined above.
    2. If the version in the DB is different, it DROPS ALL tables.
    3. Then it CREATES all tables fresh for Project 1/2.
    """
    # LOCAL IMPORT for models only
    import app.core.models as models 

    async with engine.begin() as conn:
        # Create a tiny tracker table if it doesn't exist
        await conn.execute(text("CREATE TABLE IF NOT EXISTS _schema_tracker (version TEXT)"))
        
        # Check the current version stored in the database
        res = await conn.execute(text("SELECT version FROM _schema_tracker LIMIT 1"))
        db_version = res.scalar()

        # ⭐ THE TRIGGER POINT: If version in code doesn't match version in DB
        if db_version != CURRENT_SCHEMA_VERSION:
            logger.warning(f"⚠️ SCHEMA MISMATCH: DB is '{db_version}', Code is '{CURRENT_SCHEMA_VERSION}'")
            logger.warning("🗑️  STEGMAN RULE: DELETING OLD TABLES AND STARTING FRESH...")
            
            # STEP 1: Wipe the old data
            await conn.run_sync(models.Base.metadata.drop_all)
            
            # STEP 2: Build the new tables
            await conn.run_sync(models.Base.metadata.create_all)
            
            # STEP 3: Update the version tracker
            await conn.execute(text("DELETE FROM _schema_tracker"))
            await conn.execute(
                text("INSERT INTO _schema_tracker (version) VALUES (:v)"),
                {"v": CURRENT_SCHEMA_VERSION}
            )
            logger.info(f"✅ FRESH START COMPLETE: Database is now version {CURRENT_SCHEMA_VERSION}")
        else:
            # Versions match - just ensure tables exist
            await conn.run_sync(models.Base.metadata.create_all)
            logger.info(f"🧬 Schema version {CURRENT_SCHEMA_VERSION} is current. No wipe needed.")

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
