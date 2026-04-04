import os
import logging
from typing import AsyncGenerator, Optional
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
    async_sessionmaker,
    AsyncEngine,
)
from sqlalchemy.orm import DeclarativeBase

# ---------------------------------------------------------
# LOGGING
# ---------------------------------------------------------
logger = logging.getLogger("app.core.db")

# ---------------------------------------------------------
# DECLARATIVE BASE (ISOLATED TO PREVENT CIRCULAR IMPORTS)
# ---------------------------------------------------------
class Base(DeclarativeBase):
    """
    Shared Declarative Base.
    Imported by models without triggering engine creation.
    """
    pass

# ---------------------------------------------------------
# DATABASE URL NORMALIZATION
# ---------------------------------------------------------
def _get_db_url() -> str:
    """
    Normalize DATABASE_URL for SQLAlchemy async usage.
    """
    url = os.getenv("DATABASE_URL", "").strip()
    
    # If no DATABASE_URL provided, use SQLite as fallback
    if not url:
        logger.warning("DATABASE_URL not set, using SQLite fallback: ./test.db")
        url = "sqlite+aiosqlite:///./test.db"
    
    # Convert PostgreSQL URLs to async format
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql://") and "+asyncpg" not in url:
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif url.startswith("sqlite://") and "+aiosqlite" not in url:
        url = url.replace("sqlite://", "sqlite+aiosqlite://", 1)
    
    return url


DATABASE_URL = _get_db_url()
logger.info(f"Database URL type: {DATABASE_URL.split('://')[0] if '://' in DATABASE_URL else 'unknown'}")

# ---------------------------------------------------------
# LAZY ENGINE INITIALIZATION (CRITICAL FIX)
# ---------------------------------------------------------
_engine: Optional[AsyncEngine] = None
_sessionmaker: Optional[async_sessionmaker] = None

def get_engine() -> AsyncEngine:
    """
    Lazy engine creation - only creates when first needed.
    This prevents startup crashes if database is unavailable.
    """
    global _engine
    if _engine is None:
        engine_kwargs = {
            "echo": False,
            "future": True,
            "pool_pre_ping": True,
        }
        
        # Add PostgreSQL-specific timeout
        if DATABASE_URL.startswith("postgresql+asyncpg://"):
            engine_kwargs["connect_args"] = {"command_timeout": 60}
            engine_kwargs["pool_size"] = 5
            engine_kwargs["max_overflow"] = 10
        # SQLite-specific settings
        elif DATABASE_URL.startswith("sqlite+aiosqlite://"):
            engine_kwargs["connect_args"] = {"check_same_thread": False}
        
        try:
            _engine = create_async_engine(DATABASE_URL, **engine_kwargs)
            logger.info("✅ Database engine created successfully")
        except Exception as e:
            logger.error(f"❌ Failed to create database engine: {e}")
            raise
    
    return _engine

def get_sessionmaker() -> async_sessionmaker:
    """
    Lazy sessionmaker creation.
    """
    global _sessionmaker
    if _sessionmaker is None:
        engine = get_engine()
        _sessionmaker = async_sessionmaker(
            bind=engine,
            expire_on_commit=False,
            class_=AsyncSession,
        )
        logger.info("✅ Sessionmaker created successfully")
    
    return _sessionmaker

# ---------------------------------------------------------
# BACKWARD-COMPATIBLE EXPORTS
# ---------------------------------------------------------
@property
def engine() -> AsyncEngine:
    """Property for backward compatibility - returns lazy engine"""
    return get_engine()

@property
def SessionLocal() -> async_sessionmaker:
    """Property for backward compatibility - returns lazy sessionmaker"""
    return get_sessionmaker()

# ---------------------------------------------------------
# FASTAPI DATABASE DEPENDENCY
# ---------------------------------------------------------
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Primary FastAPI dependency that yields an AsyncSession.
    """
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        try:
            yield session
        except Exception as e:
            logger.error(f"Database session error: {e}")
            await session.rollback()
            raise
        finally:
            await session.close()

# ---------------------------------------------------------
# BACKWARD-COMPATIBILITY ALIAS
# ---------------------------------------------------------
get_session = get_db

# ---------------------------------------------------------
# HEALTH CHECK FUNCTION
# ---------------------------------------------------------
async def check_db_connection() -> bool:
    """
    Check if database is reachable.
    Returns True if connected, False otherwise.
    """
    try:
        sessionmaker = get_sessionmaker()
        async with sessionmaker() as session:
            await session.execute("SELECT 1")
            logger.info("✅ Database health check passed")
            return True
    except Exception as e:
        logger.error(f"❌ Database health check failed: {e}")
        return False

# ---------------------------------------------------------
# MODEL INITIALIZATION (IMPROVED ERROR HANDLING)
# ---------------------------------------------------------
async def init_models() -> None:
    """
    Initialize database tables.
    This should be called during app lifespan.
    """
    try:
        # Import models here to avoid circular imports
        import app.core.models  # noqa: F401
        
        engine = get_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        
        logger.info("✅ Database schema initialized successfully")
        
        # Verify connection
        if not await check_db_connection():
            logger.warning("⚠️ Database connection verification failed after initialization")
    
    except ImportError as e:
        logger.error(f"❌ Failed to import models: {e}")
        raise
    except Exception as e:
        logger.exception(f"❌ Database initialization failed: {e}")
        raise

# ---------------------------------------------------------
# CLEANUP FUNCTION
# ---------------------------------------------------------
async def dispose_engine() -> None:
    """
    Properly dispose of database engine on shutdown.
    """
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _sessionmaker = None
        logger.info("✅ Database engine disposed successfully")
