# Filename: app/db.py

import os
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker, Session
from .core.config import settings
from .models import Base

# DATABASE URL
url = settings.DATABASE_URL or "sqlite:///./app.db"

# Normalize Postgres URL and use psycopg v3
if url.startswith("postgres://"):
    url = url.replace("postgres://", "postgresql://", 1)
if url.startswith("postgresql://") and "+psycopg" not in url:
    url = url.replace("postgresql://", "postgresql+psycopg://", 1)
if url.startswith("postgresql+psycopg://") and "sslmode" not in url:
    sep = "&" if "?" in url else "?"
    url = f"{url}{sep}sslmode=require"

# CREATE ENGINE
engine = create_engine(
    url,
    connect_args={"check_same_thread": False} if url.startswith("sqlite") else {},
    future=True,
    echo=False,
)

# SESSION
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)

# Dependency
def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# -----------------------------
# FLEXIBLE AUTO-CREATE TABLES
# -----------------------------
def init_db(drop_existing: bool = False):
    """
    Initialize database:
    - If drop_existing=True, drop all old tables (destructive)
    - Then create all tables based on current models.py
    """
    inspector = inspect(engine)
    if drop_existing:
        print("Dropping all existing tables...")
        Base.metadata.drop_all(bind=engine)

    print("Creating/updating tables...")
    Base.metadata.create_all(bind=engine)
    print("Database initialized successfully!")
