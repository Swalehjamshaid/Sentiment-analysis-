from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

# Requirement 124: Database Engine Initialization
# We use the DATABASE_URL and DEBUG settings from config.py
engine = create_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_pre_ping=True,  # Critical for Railway/Cloud to keep connections alive
    pool_recycle=300
)

# Factory for creating database sessions
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    """Dependency for routes to get a DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
