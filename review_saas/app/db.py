import os
from sqlalchemy import create_engine
from .core.config import settings

url = settings.DATABASE_URL or "sqlite:///./app.db"

# Normalize legacy postgres URL and prefer psycopg3 dialect for SQLAlchemy 2.x
if url.startswith("postgres://"):
    url = url.replace("postgres://", "postgresql://", 1)

# If it's a PostgreSQL URL but no explicit driver, switch to psycopg (v3).
if url.startswith("postgresql://") and "+psycopg" not in url:
    url = url.replace("postgresql://", "postgresql+psycopg://", 1)

# Managed PG: ensure sslmode=require if missing.
if url.startswith("postgresql+psycopg://") and "sslmode" not in url:
    sep = "&" if "?" in url else "?"
    url = f"{url}{sep}sslmode=require"

engine = create_engine(
    url,
    connect_args={"check_same_thread": False} if url.startswith("sqlite") else {},
    future=True,
    echo=False,
)
