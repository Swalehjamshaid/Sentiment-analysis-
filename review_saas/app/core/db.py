# filename: app/core/db.py
from __future__ import annotations
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from .settings import settings

logger = logging.getLogger('app.db')

url = settings.DATABASE_URL

# Safety Check: Detect if placeholders like 'port' or 'host' are still in the string
if ":port" in url or "@host" in url:
    logger.error("CRITICAL: DATABASE_URL still contains placeholders like ':port'. Falling back to SQLite.")
    url = "sqlite:///./app.db"

# Fix legacy 'postgres://'
if url.startswith('postgres://'):
    url = url.replace('postgres://', 'postgresql://', 1)

# Add driver for SQLAlchemy 2.x
if url.startswith('postgresql://') and '+psycopg' not in url:
    url = url.replace('postgresql://', 'postgresql+psycopg://', 1)

# Enforce SSL
if 'postgresql+psycopg' in url and 'sslmode' not in url:
    connector = '&' if '?' in url else '?'
    url = f"{url}{connector}sslmode=require"

try:
    engine = create_engine(
        url, 
        connect_args={'check_same_thread': False} if 'sqlite' in url else {}, 
        pool_pre_ping=True, 
        future=True
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
except Exception as e:
    logger.error(f"Failed to create engine with URL: {url}. Error: {e}")
    # Final fallback to prevent container crash
    engine = create_engine("sqlite:///./fallback.db", connect_args={'check_same_thread': False})
    SessionLocal = sessionmaker(bind=engine)

def init_db(Base):
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
