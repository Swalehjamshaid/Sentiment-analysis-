# filename: app/db.py
from __future__ import annotations

import logging
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.engine import URL

logger = logging.getLogger("app.db")

# -------------------------------------------------------
# DATABASE URL LOADING (Railway + Local Safe Handling)
# -------------------------------------------------------

DATABASE_URL = (
    os.getenv("DATABASE_URL")
    or os.getenv("DATABASE_PUBLIC_URL")
    or "sqlite:///./app.db"  # fallback for local MVP
)

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set.")

# Fix legacy postgres:// URLs (Railway sometimes provides this)
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace(
        "postgres://",
        "postgresql://",
        1
    )

# Ensure psycopg driver for PostgreSQL
if DATABASE_URL.startswith("postgresql://") and "+psycopg" not in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace(
        "postgresql://",
        "postgresql+psycopg://",
        1
    )

logger.info(f"Using database: {DATABASE_URL.split('@')[-1]}")

# -------------------------------------------------------
# ENGINE CREATION
# -------------------------------------------------------

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}
    if DATABASE_URL.startswith("sqlite")
    else {},
    pool_pre_ping=True,
    future=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    future=True,
)

# -------------------------------------------------------
# INIT FUNCTION (called on startup)
# -------------------------------------------------------

def init_db_sync(Base):
    logger.info("Creating database tables (if not exist)...")
    Base.metadata.create_all(bind=engine)
    logger.info("Database ready.")
