# filename: app/core/db.py

import os
import logging

from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    async_sessionmaker,
)

from sqlalchemy import text

# ==========================================================
# BASE IMPORT
# ==========================================================

from app.core.base import Base

# ==========================================================
# SCHEMA VERSION
# ==========================================================

CURRENT_SCHEMA_VERSION = "2026-05-13-V21"

# ==========================================================
# LOGGING
# ==========================================================

logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(
    "app.core.db"
)

# ==========================================================
# DATABASE URL
# ==========================================================

DATABASE_URL = os.getenv(
    "DATABASE_URL"
)

if not DATABASE_URL:

    raise RuntimeError(
        "DATABASE_URL not set"
    )

# ==========================================================
# FIX RAILWAY POSTGRES
# ==========================================================

if DATABASE_URL.startswith(
    "postgres://"
):

    DATABASE_URL = DATABASE_URL.replace(

        "postgres://",

        "postgresql+asyncpg://",

        1
    )

# ==========================================================
# ENGINE
# ==========================================================

engine = create_async_engine(

    DATABASE_URL,

    pool_pre_ping=True,

    future=True,

    echo=False
)

# ==========================================================
# SESSION FACTORY
# ==========================================================

AsyncSessionLocal = async_sessionmaker(

    bind=engine,

    class_=AsyncSession,

    expire_on_commit=False
)

# ==========================================================
# BACKWARD COMPATIBILITY
# ==========================================================

SessionLocal = AsyncSessionLocal

# ==========================================================
# DATABASE INITIALIZATION
# ==========================================================

async def init_models():

    """
    FINAL DATABASE INITIALIZATION
    """

    import app.core.models as models

    async with engine.begin() as conn:

        # ==================================================
        # CREATE SCHEMA TRACKER
        # ==================================================

        await conn.execute(

            text(
                "CREATE TABLE IF NOT EXISTS _schema_tracker (version TEXT)"
            )
        )

        # ==================================================
        # CHECK CURRENT VERSION
        # ==================================================

        result = await conn.execute(

            text(
                "SELECT version FROM _schema_tracker LIMIT 1"
            )
        )

        db_version = result.scalar()

        # ==================================================
        # SCHEMA RESET
        # ==================================================

        if db_version != CURRENT_SCHEMA_VERSION:

            logger.warning(

                f"⚠️ Schema mismatch detected | DB={db_version} | CODE={CURRENT_SCHEMA_VERSION}"
            )

            logger.warning(
                "🗑️ Starting Nuclear Reset..."
            )

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

                "config",
            ]

            for table in tables_to_wipe:

                try:

                    await conn.execute(

                        text(
                            f'DROP TABLE IF EXISTS "{table}" CASCADE'
                        )
                    )

                    logger.info(
                        f"🗑️ Dropped: {table}"
                    )

                except Exception as e:

                    logger.error(
                        f"❌ Failed dropping {table}: {e}"
                    )

            # ==============================================
            # CREATE NEW TABLES
            # ==============================================

            await conn.run_sync(
                models.Base.metadata.create_all
            )

            # ==============================================
            # UPDATE SCHEMA TRACKER
            # ==============================================

            await conn.execute(
                text("DELETE FROM _schema_tracker")
            )

            await conn.execute(

                text(
                    "INSERT INTO _schema_tracker (version) VALUES (:v)"
                ),

                {
                    "v":
                        CURRENT_SCHEMA_VERSION
                }
            )

            logger.info(
                f"✅ Database rebuilt successfully | Version={CURRENT_SCHEMA_VERSION}"
            )

        else:

            await conn.run_sync(
                models.Base.metadata.create_all
            )

            logger.info(
                f"🧬 Schema version {CURRENT_SCHEMA_VERSION} already active"
            )

# ==========================================================
# DATABASE SESSION DEPENDENCY
# ==========================================================

async def get_db():

    async with AsyncSessionLocal() as session:

        try:

            yield session

        finally:

            await session.close()

# ==========================================================
# BACKWARD COMPATIBILITY
# ==========================================================

get_session = get_db
