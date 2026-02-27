# filename: app/app/db.py
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import get_settings

logger = logging.getLogger('app.db')
settings = get_settings()
engine = create_engine(settings.database_url, echo=False, future=True, connect_args={"check_same_thread": False} if settings.database_url.startswith('sqlite') else {})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
