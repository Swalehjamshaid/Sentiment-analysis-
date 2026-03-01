# File: app/core/db.py

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.exc import SQLAlchemyError
from app.core.config import settings

Base = declarative_base()

try:
    engine = create_engine(
        settings.DATABASE_URL,
        echo=settings.DEBUG,
        future=True,
    )
except SQLAlchemyError as e:
    raise RuntimeError(f"Could not create SQLAlchemy engine: {e}")

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
