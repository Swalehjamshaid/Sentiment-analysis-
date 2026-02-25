# FILE: app/db.py

from __future__ import annotations

import logging
import os
from typing import Generator, Optional

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.sql.sqltypes import NullType

# Assuming .core.config and .models exist as per your structure
try:
    from .core.config import settings
    from .models import Base
except ImportError:
    # Fallback for isolated testing/diagnostics
    class Settings:
        DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./app.db")
    settings = Settings()
    from sqlalchemy.orm import declarative_base
    Base = declarative_base()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# -------------------------------------------------------------------
# Database URL normalization
# -------------------------------------------------------------------
url = settings.DATABASE_URL or "sqlite:///./app.db"

# Fix legacy Heroku/Docker postgres strings and enforce psycopg3
if url.startswith("postgres://"):
    url = url.replace("postgres://", "postgresql://", 1)
if url.startswith("postgresql://") and "+psycopg" not in url:
    url = url.replace("postgresql://", "postgresql+psycopg://", 1)

# Enforce SSL for production Postgres
if "postgresql+psycopg" in url and "sslmode" not in url:
    sep = "&" if "?" in url else "?"
    url = f"{url}{sep}sslmode=require"

# -------------------------------------------------------------------
# Engine & Session
# -------------------------------------------------------------------
engine = create_engine(
    url,
    # check_same_thread is only for SQLite
    connect_args={"check_same_thread": False} if "sqlite" in url else {},
    pool_pre_ping=True,    # Checks connection liveness before use
    future=True,           # Enforce SQLAlchemy 2.0 style
    echo=False,
)

SessionLocal = sessionmaker(
    bind=engine, 
    autoflush=False, 
    autocommit=False, 
    future=True
)

def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency providing a database session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# -------------------------------------------------------------------
# Schema management (Simple Migrations)
# -------------------------------------------------------------------

def _compile_type_safe(col_type, dialect) -> Optional[str]:
    """Compiles SQLAlchemy type to raw SQL string."""
    try:
        if isinstance(col_type, NullType):
            return None
        return str(col_type.compile(dialect=dialect))
    except Exception as e:
        logger.warning(f"Could not compile type {col_type!r}: {e}")
        return None

def init_db(drop_existing: bool = False) -> None:
    """
    Initializes the DB, creates tables, and adds missing columns.
    Uses CASCADE for Postgres to handle foreign key dependencies.
    """
    if drop_existing:
        logger.info("Dropping all objects with CASCADE...")
        # ─────────────────────────────────────────────────────────────
        # FIX: Force a clean wipe by dropping the public schema. 
        # This resolves (psycopg.errors.DependentObjectsStillExist).
        # ─────────────────────────────────────────────────────────────
        if "postgresql" in url:
            with engine.connect() as conn:
                conn.execute(text("DROP SCHEMA public CASCADE;"))
                conn.execute(text("CREATE SCHEMA public;"))
                conn.commit()
                logger.info("Public schema recreated successfully.")
        else:
            Base.metadata.drop_all(bind=engine)

    logger.info("Ensuring tables exist...")
    Base.metadata.create_all(bind=engine)

    inspector = inspect(engine)
    
    with engine.connect() as conn:
        for table_name, table_obj in Base.metadata.tables.items():
            if not inspector.has_table(table_name):
                continue

            existing_cols = {col["name"] for col in inspector.get_columns(table_name)}
            
            for column in table_obj.columns:
                if column.name in existing_cols:
                    continue

                sql_type = _compile_type_safe(column.type, engine.dialect)
                if not sql_type:
                    continue

                default_val = ""
                if column.server_default is not None:
                    arg = getattr(column.server_default, "arg", None)
                    if arg is not None:
                        default_val = f"DEFAULT {arg}"

                logger.info(f"Syncing: Adding {table_name}.{column.name}")
                
                stmt = text(f'ALTER TABLE "{table_name}" ADD COLUMN "{column.name}" {sql_type} {default_val}')
                
                try:
                    conn.execute(stmt)
                    conn.commit()
                except Exception as e:
                    logger.error(f"Failed to add {column.name} to {table_name}: {e}")

    logger.info("Database sync complete.")
