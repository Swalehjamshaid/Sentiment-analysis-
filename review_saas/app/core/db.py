# ==========================================================
# FILE: app/core/db.py
# TRUSTLYTICS AI — FINAL STABLE DATABASE CONFIG
# MAY 2026 ENTERPRISE VERSION
# ==========================================================

import os
import logging

from sqlalchemy import text

from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    async_sessionmaker,
)

# ==========================================================
# BASE + MODELS IMPORT
# ==========================================================

from app.core.base import Base

# ==========================================================
# VERY IMPORTANT
# SAFE MODEL LOADING
# PREVENTS CIRCULAR IMPORT ISSUES
# ==========================================================

import app.core.models

# ==========================================================
# LOGGING
# ==========================================================

logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(
    "app.core.db"
)

# ==========================================================
# SCHEMA VERSION
# ==========================================================

CURRENT_SCHEMA_VERSION = "2026-05-15-V1"

# ==========================================================
# DATABASE URL
# ==========================================================

DATABASE_URL = os.getenv(
    "DATABASE_URL"
)

if not DATABASE_URL:

    raise RuntimeError(
        "❌ DATABASE_URL not set"
    )

# ==========================================================
# FIX RAILWAY POSTGRES URL
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
# DATABASE ENGINE
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
    SAFE DATABASE INITIALIZATION
    """

    try:

        async with engine.begin() as conn:

            # ==================================================
            # CREATE SCHEMA TRACKER
            # ==================================================

            await conn.execute(

                text(
                    """
                    CREATE TABLE IF NOT EXISTS _schema_tracker (
                        version TEXT
                    )
                    """
                )

            )

            # ==================================================
            # GET CURRENT SCHEMA VERSION
            # ==================================================

            result = await conn.execute(

                text(
                    """
                    SELECT version
                    FROM _schema_tracker
                    LIMIT 1
                    """
                )

            )

            db_version = result.scalar()

            # ==================================================
            # VERSION CHECK
            # ==================================================

            if db_version != CURRENT_SCHEMA_VERSION:

                logger.warning(

                    f"⚠️ Schema mismatch | DB={db_version} | CODE={CURRENT_SCHEMA_VERSION}"

                )

            else:

                logger.info(

                    f"🧬 Schema version {CURRENT_SCHEMA_VERSION} already active"

                )

            # ==================================================
            # CREATE TABLES
            # ==================================================

            await conn.run_sync(
                Base.metadata.create_all
            )

            # ==================================================
            # UPDATE SCHEMA TRACKER
            # ==================================================

            await conn.execute(

                text(
                    "DELETE FROM _schema_tracker"
                )

            )

            await conn.execute(

                text(
                    """
                    INSERT INTO _schema_tracker (version)
                    VALUES (:v)
                    """
                ),

                {
                    "v":
                        CURRENT_SCHEMA_VERSION
                }

            )

            logger.info(
                "✅ Database initialized successfully"
            )

    except Exception as e:

        logger.error(
            f"❌ Database initialization failed: {e}"
        )

        raise e

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

async def get_session():

    async for session in get_db():

        yield session

# ==========================================================
# DATABASE HEALTH CHECK
# ==========================================================

async def check_database_connection():

    """
    DATABASE CONNECTION TEST
    """

    try:

        async with engine.begin() as conn:

            await conn.execute(
                text("SELECT 1")
            )

        logger.info(
            "✅ Database connection healthy"
        )

        return True

    except Exception as e:

        logger.error(
            f"❌ Database connection failed: {e}"
        )

        return False

# ==========================================================
# CLEAN SHUTDOWN
# ==========================================================

async def close_database():

    """
    CLOSE DATABASE ENGINE
    """

    try:

        await engine.dispose()

        logger.info(
            "🛑 Database engine closed"
        )

    except Exception as e:

        logger.error(
            f"❌ Database shutdown failed: {e}"
        )
