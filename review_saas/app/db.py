# Filename: app/db.py
# Purpose: Configure SQLAlchemy engine, sessions, and ensure PostgreSQL setup is robust

import logging
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import OperationalError
from .core.config import settings
from .models import Base

logger = logging.getLogger(__name__)

# -------------------------------------------------------
# DATABASE URL CONFIGURATION
# -------------------------------------------------------
url = settings.DATABASE_URL or "sqlite:///./app.db"

# Normalize legacy Postgres URL
if url.startswith("postgres://"):
    url = url.replace("postgres://", "postgresql://", 1)

# Prefer psycopg3 for SQLAlchemy 2.x
if url.startswith("postgresql://") and "+psycopg" not in url:
    url = url.replace("postgresql://", "postgresql+psycopg://", 1)

# Ensure SSL for managed PostgreSQL
if url.startswith("postgresql+psycopg://") and "sslmode" not in url:
    sep = "&" if "?" in url else "?"
    url = f"{url}{sep}sslmode=require"

logger.info(f"Using database URL: {url}")

# -------------------------------------------------------
# SQLALCHEMY ENGINE
# -------------------------------------------------------
engine = create_engine(
    url,
    future=True,
    echo=False,
    connect_args={"check_same_thread": False} if url.startswith("sqlite") else {},
    pool_pre_ping=True,  # Auto-check connection health
)

# -------------------------------------------------------
# SESSION FACTORY
# -------------------------------------------------------
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    future=True,
)

# -------------------------------------------------------
# FASTAPI DEPENDENCY
# -------------------------------------------------------
def get_db() -> Session:
    """
    Provide a SQLAlchemy session for FastAPI dependency injection.
    Example usage: `db: Session = Depends(get_db)`
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# -------------------------------------------------------
# OPTIONAL: AUTOMATIC TABLE CREATION ON STARTUP
# -------------------------------------------------------
def init_db(drop_existing: bool = False):
    """
    Initialize the database.
    drop_existing=True -> Drop all tables first (complete reset)
    """
    try:
        if drop_existing:
            logger.warning("Dropping all existing tables...")
            with engine.begin() as conn:
                conn.execute("DROP SCHEMA public CASCADE;")
                conn.execute("CREATE SCHEMA public;")
            logger.info("All old tables dropped.")

        logger.info("Creating tables from models...")
        Base.metadata.create_all(bind=engine)
        logger.info("Tables created successfully.")

    except OperationalError as e:
        logger.error("Database initialization failed: %s", str(e))
        raise

# -------------------------------------------------------
# EVENT: OPTIONAL AUTO INIT
# -------------------------------------------------------
# Uncomment below to auto-init tables on app startup
# init_db(drop_existing=False)
