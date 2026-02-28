# filename: app/core/db.py
from __future__ import annotations
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from .settings import settings

logger = logging.getLogger('app.db')

# 1. Fetch URL and handle empty string fallback
url = settings.DATABASE_URL
if not url or url.strip() == "":
    url = 'sqlite:///./app.db'
    logger.warning("DATABASE_URL is empty. Falling back to SQLite.")

# 2. Fix legacy 'postgres://' prefix
if url.startswith('postgres://'):
    url = url.replace('postgres://', 'postgresql://', 1)

# 3. Add driver prefix if missing for SQLAlchemy 2.x
if url.startswith('postgresql://') and '+psycopg' not in url:
    url = url.replace('postgresql://', 'postgresql+psycopg://', 1)

# 4. Enforce SSL for production (Requirement 18)
if 'postgresql+psycopg' in url and 'sslmode' not in url:
    connector = '&' if '?' in url else '?'
    url = f"{url}{connector}sslmode=require"

logger.info(f"Connecting to database type: {url.split(':')[0]}")

engine = create_engine(
    url, 
    connect_args={'check_same_thread': False} if 'sqlite' in url else {}, 
    pool_pre_ping=True, 
    future=True
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

def init_db(Base):
    logger.info('Ensuring tables exist...')
    Base.metadata.create_all(bind=engine)
    logger.info('Database sync complete.')

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
