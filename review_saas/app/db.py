# filename: app/db.py
from __future__ import annotations
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from .core.config import settings

logger = logging.getLogger("app.db")

url = settings.DATABASE_URL
if url.startswith("postgres://"):
    url = url.replace("postgres://", "postgresql://", 1)
if url.startswith("postgresql://") and "+psycopg" not in url:
    url = url.replace("postgresql://", "postgresql+psycopg://", 1)

engine = create_engine(
    url,
    connect_args={"check_same_thread": False} if "sqlite" in url else {},
    pool_pre_ping=True,
    future=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

# Called at startup

def init_db_sync(Base):
    logger.info("Ensuring tables exist...")
    Base.metadata.create_all(bind=engine)
    logger.info("Database sync complete.")
