# filename: app/core/db.py
import os
import logging
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import text

# Assuming Base is in app.core.base
from app.core.base import Base

# -----------------------------------------------------------------------------
# ⭐ STEGMAN RULE: SCHEMA VERSIONING
# POINT OF CHANGE: Change this string to trigger the Nuclear Reset.
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
# ⭐ THE STEGMAN RULE: NUCLEAR WIPE & REBUILD LOGIC
# -----------------------------------------------------------------------------
async def init_models():
    """
    ✅ FINAL SCHEMA RULE:
    1. Uses CASCADE to force-drop all tables, even if they have dependencies.
    2. Wipes every table visible in the Railway Dashboard.
    3. Rebuilds fresh models for Project 1 & 2.
    """
    import app.core.models as models 

    async with engine.begin() as conn:
        # Create tracker table
        await conn.execute(text("CREATE TABLE IF NOT EXISTS _schema_tracker (version TEXT)"))
        
        # Check current DB version
        res = await conn.execute(text("SELECT version FROM _schema_tracker LIMIT 1"))
        db_version = res.scalar()

        # If mismatch, trigger the Nuclear Reset
        if db_version != CURRENT_SCHEMA_VERSION:
            logger.warning(f"⚠️ SCHEMA MISMATCH: DB='{db_version}', Code='{CURRENT_SCHEMA_VERSION}'")
            logger.warning("🗑️  STEGMAN RULE: EXECUTING BRUTE FORCE CASCADE DELETE...")
            
            # THE FIX: Explicitly drop every table that could block the reset
            # This list is based on your specific Railway Screenshot
            tables_to_wipe = [
                "competitors", 
                "company_cids", 
                "google_reviews", 
                "google_reviews_raw", 
                "reviews", 
                "audit_logs", 
                "notifications", 
                "companies", 
                "users", 
                "verification_tokens", 
                "config"
            ]
            
            for table in tables_to_wipe:
                try:
                    # CASCADE breaks the foreign key links (Dependent Objects)
                    await conn.execute(text(f'DROP TABLE IF EXISTS "{table}" CASCADE'))
                except Exception as e:
                    logger.error(f"⚠️ Could not drop {table}: {e}")

            # Build all tables fresh from your current models.py
            await conn.run_sync(models.Base.metadata.create_all)
            
            # Update Tracker with the new version
            await conn.execute(text("DELETE FROM _schema_tracker"))
            await conn.execute(
                text("INSERT INTO _schema_tracker (version) VALUES (:v)"),
                {"v": CURRENT_SCHEMA_VERSION}
            )
            logger.info(f"✅ NUCLEAR RESET COMPLETE: Database is now version {CURRENT_SCHEMA_VERSION}")
        else:
            # Standard startup - ensure everything exists
            await conn.run_sync(models.Base.metadata.create_all)
            logger.info(f"🧬 Schema version {CURRENT_SCHEMA_VERSION} is current. Ready for OPSI.")

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
