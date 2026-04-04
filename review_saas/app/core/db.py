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
# DECLARATIVE BASE
# ---------------------------------------------------------
class Base(DeclarativeBase):
    pass

# ---------------------------------------------------------
# DATABASE URL NORMALIZATION
# ---------------------------------------------------------
def _get_db_url() -> str:
    url = os.getenv("DATABASE_URL", "").strip()
    
    if not url:
        logger.warning("DATABASE_URL not set, using SQLite fallback: ./test.db")
        url = "sqlite+aiosqlite:///./test.db"
    
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
# LAZY INITIALIZATION (BUT WITH DIRECT EXPORTS)
# ---------------------------------------------------------
_engine: Optional[AsyncEngine] = None
_SessionLocal: Optional[async_sessionmaker] = None

def _create_engine() -> AsyncEngine:
    """Create the database engine (called lazily)"""
    engine_kwargs = {
        "echo": False,
        "future": True,
        "pool_pre_ping": True,
    }
    
    if DATABASE_URL.startswith("postgresql+asyncpg://"):
        engine_kwargs["connect_args"] = {"command_timeout": 60}
        engine_kwargs["pool_size"] = 5
        engine_kwargs["max_overflow"] = 10
    elif DATABASE_URL.startswith("sqlite+aiosqlite://"):
        engine_kwargs["connect_args"] = {"check_same_thread": False}
    
    try:
        engine = create_async_engine(DATABASE_URL, **engine_kwargs)
        logger.info("✅ Database engine created successfully")
        return engine
    except Exception as e:
        logger.error(f"❌ Failed to create database engine: {e}")
        raise

def _get_engine() -> AsyncEngine:
    """Lazy engine getter"""
    global _engine
    if _engine is None:
        _engine = _create_engine()
    return _engine

def _get_session_local() -> async_sessionmaker:
    """Lazy sessionmaker getter"""
    global _SessionLocal
    if _SessionLocal is None:
        engine = _get_engine()
        _SessionLocal = async_sessionmaker(
            bind=engine,
            expire_on_commit=False,
            class_=AsyncSession,
        )
        logger.info("✅ Sessionmaker created successfully")
    return _SessionLocal

# ---------------------------------------------------------
# DIRECT EXPORTS FOR MAIN.PY (BACKWARD COMPATIBLE)
# ---------------------------------------------------------
@property
def engine() -> AsyncEngine:
    """Direct engine access (as property)"""
    return _get_engine()

@property
def SessionLocal() -> async_sessionmaker:
    """Direct SessionLocal access (as property)"""
    return _get_session_local()

# Also export as functions for direct import
engine = _get_engine()
SessionLocal = _get_session_local()

# ---------------------------------------------------------
# FASTAPI DATABASE DEPENDENCY
# ---------------------------------------------------------
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Primary FastAPI dependency that yields an AsyncSession"""
    sessionmaker = _get_session_local()
    async with sessionmaker() as session:
        try:
            yield session
        except Exception as e:
            logger.error(f"Database session error: {e}")
            await session.rollback()
            raise
        finally:
            await session.close()

get_session = get_db

# ---------------------------------------------------------
# HEALTH CHECK
# ---------------------------------------------------------
async def check_db_connection() -> bool:
    """Check if database is reachable"""
    try:
        sessionmaker = _get_session_local()
        async with sessionmaker() as session:
            await session.execute("SELECT 1")
            logger.info("✅ Database health check passed")
            return True
    except Exception as e:
        logger.error(f"❌ Database health check failed: {e}")
        return False

# ---------------------------------------------------------
# MODEL INITIALIZATION
# ---------------------------------------------------------
async def init_models() -> None:
    """Initialize database tables"""
    try:
        import app.core.models  # noqa: F401
        
        engine = _get_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        
        logger.info("✅ Database schema initialized successfully")
        
        if not await check_db_connection():
            logger.warning("⚠️ Database connection verification failed after initialization")
    
    except ImportError as e:
        logger.error(f"❌ Failed to import models: {e}")
        raise
    except Exception as e:
        logger.exception(f"❌ Database initialization failed: {e}")
        raise

# ---------------------------------------------------------
# CLEANUP
# ---------------------------------------------------------
async def dispose_engine() -> None:
    """Properly dispose of database engine on shutdown"""
    global _engine, _SessionLocal
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _SessionLocal = None
        logger.info("✅ Database engine disposed successfully")
