
# filename: app/core/db.py
from __future__ import annotations
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from .settings import settings

logger = logging.getLogger('app.db')

url = settings.DATABASE_URL
if url.startswith('postgres://'):
    url = url.replace('postgres://', 'postgresql://', 1)
if url.startswith('postgresql://') and '+psycopg' not in url:
    url = url.replace('postgresql://', 'postgresql+psycopg://', 1)
if 'postgresql+psycopg' in url and 'sslmode' not in url:
    url = url + ('&sslmode=require' if '?' in url else '?sslmode=require')

engine = create_engine(url, connect_args={'check_same_thread': False} if 'sqlite' in url else {}, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

# Simple init hook used at startup

def init_db(Base):
    logger.info('Ensuring tables exist...')
    Base.metadata.create_all(bind=engine)
    logger.info('Database sync complete.')

# Dependency for FastAPI

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
