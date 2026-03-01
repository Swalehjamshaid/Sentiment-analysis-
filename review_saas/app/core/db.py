# filename: app/core/db.py
import os
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session

logger = logging.getLogger("app.db")

def _resolve_db_url() -> str:
    # 1. Fetch the URL from Railway Environment Variables
    url = os.getenv("DATABASE_URL") or os.getenv("DATABASE_PUBLIC_URL")
    
    if not url or "placeholder" in url.lower():
        logger.warning("No Postgres URL found. Falling back to local SQLite.")
        return "sqlite:///./review_saas.db"
    
    # 2. HOLISTIC FIX: Force SQLAlchemy to use the Psycopg 3 driver
    # This prevents the 'psycopg2' ModuleNotFoundError
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
        
    return url

DATABASE_URL = _resolve_db_url()

# pool_pre_ping=True is essential for Railway to keep Postgres connections alive
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=engine))

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db(Base):
    """Creates tables in the PostgreSQL database if they don't exist."""
    Base.metadata.create_all(bind=engine)
