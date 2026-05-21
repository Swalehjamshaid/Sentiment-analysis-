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
# BASE + MODELS IMPORT
# ==========================================================

from app.core.base import Base

# VERY IMPORTANT
# FORCE LOAD ALL MODELS
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
    SAFE DATABASE INITIALIZATION
    """

    try:

        async with engine.begin() as conn:

            # ==============================================
            # CREATE SCHEMA TRACKER TABLE
            # ==============================================

            await conn.execute(

                text(
                    """
                    CREATE TABLE IF NOT EXISTS _schema_tracker (
                        version TEXT
                    )
                    """
                )

            )

            # ==============================================
            # GET CURRENT DATABASE VERSION
            # ==============================================

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

            # ==============================================
            # SCHEMA VERSION CHECK
            # ==============================================

            if db_version != CURRENT_SCHEMA_VERSION:

                logger.warning(

                    f"⚠️ Schema update detected | DB={db_version} | CODE={CURRENT_SCHEMA_VERSION}"

                )

            else:

                logger.info(

                    f"🧬 Schema version {CURRENT_SCHEMA_VERSION} already active"

                )

            # ==============================================
            # CREATE TABLES SAFELY
            # ==============================================

            await conn.run_sync(
                Base.metadata.create_all
            )

            # ==============================================
            # UPDATE SCHEMA TRACKER
            # ==============================================

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
    async def get_session():
    async for session in get_db():
        yield session

    async with AsyncSessionLocal() as session:

        try:

            yield session

        finally:

            await session.close()

# ==========================================================
# BACKWARD COMPATIBILITY
# ==========================================================

get_session = get_db
