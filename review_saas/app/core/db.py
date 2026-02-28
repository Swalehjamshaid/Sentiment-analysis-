# File: app/core/db.py
from __future__ import annotations
import logging
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.exc import OperationalError
from app.core.settings import settings

logger = logging.getLogger("app.db")

def _resolve_db_url() -> str:
    url = settings.DATABASE_URL or os.getenv("DATABASE_URL") or ""
    # Detect placeholders or empties; fall back to SQLite
    if (not url) or ("postgresql+psycopg://user:pass@" in url) or ("PLACEHOLDER" in url):
        logger.warning("DATABASE_URL contains placeholders or is empty. Falling back to SQLite.")
        os.makedirs("app", exist_ok=True)
        return "sqlite:///app/data.db"
    return url

DATABASE_URL = _resolve_db_url()

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
    pool_pre_ping=True,
)

SessionLocal = scoped_session(
    sessionmaker(autocommit=False, autoflush=False, bind=engine)
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db(Base):
    """Create all tables for the provided SQLAlchemy Base."""
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database synchronized.")
    except OperationalError as e:
        logger.error(f"Database initialization failed: {e}")
