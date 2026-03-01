import os
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from app.core.settings import settings

logger = logging.getLogger("app.db")

def _resolve_db_url() -> str:
    # 1. Check Railway's specific variables
    url = os.getenv("DATABASE_URL") or os.getenv("DATABASE_PUBLIC_URL") or settings.DATABASE_URL or ""
    
    if not url or "placeholder" in url.lower():
        logger.warning("No Postgres URL found. Falling back to SQLite.")
        return "sqlite:///./review_saas.db"
    
    # 2. Fix Dialect for SQLAlchemy 2.0
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url

DATABASE_URL = _resolve_db_url()
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=engine))

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db(Base):
    Base.metadata.create_all(bind=engine)
