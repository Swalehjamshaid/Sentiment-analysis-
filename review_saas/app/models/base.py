# File: review_saas/app/core/db.py
import os
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from .settings import settings

logger = logging.getLogger("review_saas")

def get_engine_url():
    """
    Retrieves the database URL and handles common environment mismatches.
    Requirement #124: Production-ready database handling.
    """
    url = settings.DATABASE_URL
    
    # Check for empty or placeholder variables from logs
    if not url or "placeholder" in url.lower() or "user:password" in url:
        logger.warning("DATABASE_URL is missing or invalid. Falling back to SQLite for local development.")
        return "sqlite:///./review_saas.db"
    
    # Fix: Railway and Heroku often provide 'postgres://', but SQLAlchemy requires 'postgresql://'
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
        
    return url

# Create engine with connection pooling
engine = create_engine(
    get_engine_url(),
    # check_same_thread is only required for SQLite
    connect_args={"check_same_thread": False} if "sqlite" in get_engine_url() else {}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db(base_model):
    """
    Synchronizes the database schema using the centralized Base.
    Requirement #124: Auto-sync on startup.
    """
    try:
        # Uses the Base from app/models/base.py
        base_model.metadata.create_all(bind=engine)
        logger.info("app.db: Database synchronized.")
    except Exception as e:
        logger.error(f"Database synchronization failed: {e}")

def get_db():
    """
    FastAPI dependency to provide a database session to routes.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
