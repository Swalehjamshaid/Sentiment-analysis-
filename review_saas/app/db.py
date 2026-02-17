# app/db.py

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from .core.config import settings

# Database URL with default fallback
url = settings.DATABASE_URL or "sqlite:///./app.db"

# Normalize legacy postgres URL and prefer psycopg3 dialect for SQLAlchemy 2.x
if url.startswith("postgres://"):
    url = url.replace("postgres://", "postgresql://", 1)

# If it's PostgreSQL URL but no explicit driver, switch to psycopg (v3)
if url.startswith("postgresql://") and "+psycopg" not in url:
    url = url.replace("postgresql://", "postgresql+psycopg://", 1)

# Managed PG: ensure sslmode=require if missing
if url.startswith("postgresql+psycopg://") and "sslmode" not in url:
    sep = "&" if "?" in url else "?"
    url = f"{url}{sep}sslmode=require"

# SQLAlchemy Engine
engine = create_engine(
    url,
    connect_args={"check_same_thread": False} if url.startswith("sqlite") else {},
    future=True,
    echo=False,
)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)

# Dependency function for FastAPI
def get_db() -> Session:
    """
    Provide a SQLAlchemy session for dependency injection.
    Usage in FastAPI: `db: Session = Depends(get_db)`
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
