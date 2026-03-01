# filename: app/core/db.py

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

try:
    if not settings.DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL is empty. Please set it in your .env file."
        )

    engine = create_engine(
        settings.DATABASE_URL,
        echo=settings.DEBUG,
        future=True,
    )

    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
except Exception as e:
    raise RuntimeError(f"Could not create SQLAlchemy engine: {e}")
