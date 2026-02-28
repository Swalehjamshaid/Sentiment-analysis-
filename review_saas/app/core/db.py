# filename: app/core/db.py
from __future__ import annotations
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from .settings import settings

logger = logging.getLogger('app.db')

def get_engine_url():
    url = settings.DATABASE_URL
    
    # Handle Railway/Empty string edge cases
    if not url or url.strip() == "" or ":port" in url:
        logger.warning("DATABASE_URL invalid or empty. Falling back to SQLite.")
        return 'sqlite:///./app.db'

    # Fix legacy 'postgres://' for SQLAlchemy 2.0
    if url.startswith('postgres://'):
        url = url.replace('postgres://', 'postgresql://', 1)
    
    # Ensure modern psycopg driver is specified
    if url.startswith('postgresql://') and '+psycopg' not in url:
        url = url.replace('postgresql://', 'postgresql+psycopg://', 1)
        
    # Requirement #18: Enforce SSL for Production DB
    if 'postgresql+psycopg' in url and 'sslmode' not in url:
        connector = '&' if '?' in url else '?'
        url = f"{url}{connector}sslmode=require"
        
    return url

final_url = get_engine_url()

engine = create_engine(
    final_url, 
    connect_args={'check_same_thread': False} if 'sqlite' in final_url else {}, 
    pool_pre_ping=True, 
    future=True
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

def init_db(Base):
    logger.info(f"Initializing database at: {final_url.split('@')[-1] if '@' in final_url else final_url}")
    Base.metadata.create_all(bind=engine)
    logger.info('Database sync complete.')

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
