# filename: app/core/db.py
from __future__ import annotations
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from .settings import settings

logger = logging.getLogger('app.db')

def get_db_url():
    url = settings.DATABASE_URL
    if not url or ":port" in url:
        logger.warning("DATABASE_URL contains placeholders or is empty. Falling back to SQLite.")
        return 'sqlite:///./app.db'
    
    if url.startswith('postgres://'):
        url = url.replace('postgres://', 'postgresql://', 1)
    
    if url.startswith('postgresql://') and '+psycopg' not in url:
        url = url.replace('postgresql://', 'postgresql+psycopg://', 1)
        
    if 'postgresql+psycopg' in url and 'sslmode' not in url:
        connector = '&' if '?' in url else '?'
        url = f"{url}{connector}sslmode=require"
        
    return url

db_url = get_db_url()
engine = create_engine(
    db_url, 
    connect_args={'check_same_thread': False} if 'sqlite' in db_url else {}, 
    pool_pre_ping=True, 
    future=True
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

def init_db(Base):
    Base.metadata.create_all(bind=engine)
    logger.info("Database synchronized.")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
