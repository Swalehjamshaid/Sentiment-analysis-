
from __future__ import annotations

import logging
import os
from typing import Generator, Optional

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.sql.sqltypes import NullType

try:
    from .core.config import settings
    from .models import Base
except ImportError:
    class Settings:
        DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./app.db")
    settings = Settings()
    from sqlalchemy.orm import declarative_base
    Base = declarative_base()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app.db")

# Normalize DB URL
url = settings.DATABASE_URL or "sqlite:///./app.db"
if url.startswith("postgres://"):
    url = url.replace("postgres://", "postgresql://", 1)
if url.startswith("postgresql://") and "+psycopg" not in url:
    url = url.replace("postgresql://", "postgresql+psycopg://", 1)
if "postgresql+psycopg" in url and "sslmode" not in url:
    sep = "&" if "?" in url else "?"
    url = f"{url}{sep}sslmode=require"

engine = create_engine(
    url,
    connect_args={"check_same_thread": False} if "sqlite" in url else {},
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=2,
    pool_timeout=15,
    pool_recycle=1800,
    future=True,
    echo=False,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

RUN_COLUMN_SYNC = os.getenv("RUN_COLUMN_SYNC", "1") == "1"

def _compile_type_safe(col_type, dialect) -> Optional[str]:
    try:
        if isinstance(col_type, NullType):
            return None
        return str(col_type.compile(dialect=dialect))
    except Exception as e:
        logger.warning(f"Could not compile type {col_type!r}: {e}")
        return None

def init_db(drop_existing: bool = False) -> None:
    if drop_existing:
        logger.info("Dropping all tables...")
        Base.metadata.drop_all(bind=engine)

    logger.info("Ensuring tables exist...")
    Base.metadata.create_all(bind=engine)

    if not RUN_COLUMN_SYNC:
        logger.info("Column sync disabled (RUN_COLUMN_SYNC=0).")
        logger.info("Database sync complete.")
        return

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

                logger.info(f"Syncing: Adding {table_name}.{column.name}")
                stmt = text(f'ALTER TABLE "{table_name}" ADD COLUMN "{column.name}" {sql_type}')
                try:
                    conn.execute(stmt)
                    conn.commit()
                except Exception as e:
                    logger.error(f"Failed to add {column.name} to {table_name}: {e}")

    logger.info("Database sync complete.")
