# File: app/core/db.py

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from app.core.config import settings  # your DB URL comes from here

# SQLAlchemy Base
Base = declarative_base()

# Engine
engine = create_engine(
    settings.DATABASE_URL,
    echo=getattr(settings, "DEBUG", False),
    future=True,  # SQLAlchemy 2.0 style
)

# Session factory
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

# Optional: init_db helper
def init_db(base: Base):
    """Create all tables."""
    base.metadata.create_all(bind=engine)
