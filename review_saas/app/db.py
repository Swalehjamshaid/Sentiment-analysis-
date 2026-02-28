# filename: app/db.py
from __future__ import annotations

import logging
from typing import Generator, Optional

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker, Session

from .core.config import settings
from .models import Base

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app.db")

# -------------------------------------------------------------------
# Database URL normalization
# -------------------------------------------------------------------
def _normalized_url(raw: str) -> str:
    url = raw or "sqlite:///./app.db"

    # Heroku-style prefix
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    # Enforce psycopg3 driver for SQLAlchemy 2.x
    if url.startswith("postgresql://") and "+psycopg" not in url:
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    # Require SSL in production unless explicitly disabled
    if "postgresql+psycopg" in url and "sslmode" not in url:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}sslmode=require"
    return url

DB_URL = _normalized_url(getattr(settings, "DATABASE_URL", getattr(settings, "database_url", "sqlite:///./app.db")))

# -------------------------------------------------------------------
# Engine & Session
# -------------------------------------------------------------------
engine = create_engine(
    DB_URL,
    connect_args={"check_same_thread": False} if DB_URL.startswith("sqlite") else {},
    pool_pre_ping=True,
    future=True,
    echo=False,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

def get_db() -> Generator[Session, None, None]:
    """General-purpose session provider (usable in background jobs or APIs)."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# -------------------------------------------------------------------
# Schema management
# -------------------------------------------------------------------
def init_db(app: Optional[object] = None, drop_existing: bool = False) -> None:
    """
    Initialize database and create tables from app.models.Base.
    If a Flask app object is passed, you can store engine/session in app config if desired.
    """
    if drop_existing:
        logger.info("Dropping all tables...")
        Base.metadata.drop_all(bind=engine)

    logger.info("Ensuring tables exist...")
    Base.metadata.create_all(bind=engine)

    # (Optional) basic verification
    insp = inspect(engine)
    missing = [t for t in Base.metadata.tables if not insp.has_table(t)]
    if missing:
        logger.warning("Some tables are still missing after create_all: %s", ", ".join(missing))
    else:
        logger.info("Database sync complete.")
