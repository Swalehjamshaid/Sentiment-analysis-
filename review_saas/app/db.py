# Filename: app/db.py

import os
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, Session
from .core.config import settings
from .models import Base
from sqlalchemy import Column
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database URL
url = settings.DATABASE_URL or "sqlite:///./app.db"

# Normalize legacy postgres URL and prefer psycopg3 dialect for SQLAlchemy 2.x
if url.startswith("postgres://"):
    url = url.replace("postgres://", "postgresql://", 1)
if url.startswith("postgresql://") and "+psycopg" not in url:
    url = url.replace("postgresql://", "postgresql+psycopg://", 1)
if url.startswith("postgresql+psycopg://") and "sslmode" not in url:
    sep = "&" if "?" in url else "?"
    url = f"{url}{sep}sslmode=require"

# SQLAlchemy Engine
engine = create_engine(
    url,
    connect_args={"check_same_thread": False} if url.startswith("sqlite") else {},
    future=True,
    echo=False,
)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)

# Dependency
def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db(drop_existing: bool = False):
    """
    Initialize database:
    - drop_existing: Drop all tables first (destructive)
    - Create tables if missing
    - Automatically add missing columns to existing tables
    """
    if drop_existing:
        logger.info("Dropping all tables...")
        Base.metadata.drop_all(bind=engine)
        logger.info("All tables dropped.")

    logger.info("Creating missing tables...")
    Base.metadata.create_all(bind=engine)
    logger.info("Tables created if missing.")

    # Auto-add missing columns
    inspector = inspect(engine)
    with engine.begin() as conn:
        for table_name, table_obj in Base.metadata.tables.items():
            if not inspector.has_table(table_name):
                continue
            existing_columns = [col["name"] for col in inspector.get_columns(table_name)]
            for column in table_obj.columns:
                if column.name not in existing_columns:
                    col_type = column.type.compile(dialect=engine.dialect)
                    nullable = "NULL" if column.nullable else "NOT NULL"
                    default = ""
                    if column.default is not None:
                        if hasattr(column.default, 'arg'):
                            default_val = column.default.arg
                        else:
                            default_val = column.default
                        default = f"DEFAULT {default_val}"
                    sql = f'ALTER TABLE {table_name} ADD COLUMN {column.name} {col_type} {nullable} {default};'
                    try:
                        logger.info(f"Adding missing column `{column.name}` to table `{table_name}`")
                        conn.execute(text(sql))
                    except Exception as e:
                        logger.error(f"Failed to add column `{column.name}`: {e}")
