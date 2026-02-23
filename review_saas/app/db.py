# Filename: app/db.py

from __future__ import annotations

import logging
from typing import Generator, Optional

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.sql.sqltypes import NullType

from .core.config import settings
from .models import Base

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# -------------------------------------------------------------------
# Database URL normalization
# -------------------------------------------------------------------
url = settings.DATABASE_URL or "sqlite:///./app.db"

# Normalize legacy postgres URL and prefer psycopg3 dialect for SQLAlchemy 2.x
if url.startswith("postgres://"):
    url = url.replace("postgres://", "postgresql://", 1)
if url.startswith("postgresql://") and "+psycopg" not in url:
    url = url.replace("postgresql://", "postgresql+psycopg://", 1)
if url.startswith("postgresql+psycopg://") and "sslmode" not in url:
    sep = "&" if "?" in url else "?"
    url = f"{url}{sep}sslmode=require"

# -------------------------------------------------------------------
# Engine & Session
# -------------------------------------------------------------------
engine = create_engine(
    url,
    connect_args={"check_same_thread": False} if url.startswith("sqlite") else {},
    pool_pre_ping=True,           # mitigate stale connections
    future=True,
    echo=False,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency to provide a scoped Session.
    Ensures the session is closed after the request lifecycle.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# -------------------------------------------------------------------
# Schema management
# -------------------------------------------------------------------
def _compile_type_safe(col_type, dialect) -> Optional[str]:
    """
    Compile a SQLAlchemy column type to a SQL string. Returns None for unknown types.
    """
    try:
        # Some types may be dialect-specific; NullType means SQLAlchemy didn't infer a type.
        if isinstance(col_type, NullType):
            return None
        return col_type.compile(dialect=dialect)
    except Exception as e:
        logger.warning(f"Could not compile column type {col_type!r}: {e}")
        return None


def _can_add_not_null_without_default(column) -> bool:
    """
    Returns True if adding a NOT NULL column without default is safe (generally not).
    We conservatively reject this to avoid failing ALTER TABLE on existing rows.
    """
    server_default = getattr(column, "server_default", None)
    default = getattr(column, "default", None)
    return bool(server_default or default)


def init_db(drop_existing: bool = False) -> None:
    """
    Initialize database:
    - drop_existing: Drop all tables first (destructive)
    - Create tables if missing
    - Automatically add missing columns to existing tables (best-effort & safe)

    NOTE:
      * For complex migrations (renames, constraints, non-null without defaults),
        prefer using Alembic. This helper only handles simple additive changes.
    """
    if drop_existing:
        logger.info("Dropping all tables...")
        Base.metadata.drop_all(bind=engine)
        logger.info("All tables dropped.")

    logger.info("Creating missing tables...")
    Base.metadata.create_all(bind=engine)
    logger.info("Tables created if missing.")

    # Best-effort: add missing columns
    inspector = inspect(engine)

    with engine.begin() as conn:
        for table_name, table_obj in Base.metadata.tables.items():
            # Skip tables that do not exist (create_all normally created them)
            if not inspector.has_table(table_name):
                continue

            existing_cols = {col["name"] for col in inspector.get_columns(table_name)}
            for column in table_obj.columns:
                if column.name in existing_cols:
                    continue

                # Compile SQL type
                sql_type = _compile_type_safe(column.type, engine.dialect)
                if not sql_type:
                    logger.warning(
                        f"[{table_name}.{column.name}] Unknown type; "
                        f"skip auto-add. Define an explicit migration."
                    )
                    continue

                # Strategy:
                # 1) Add column as NULLABLE to avoid failures for existing rows
                # 2) If a server_default exists, include it
                # 3) Do NOT enforce NOT NULL here unless a default is guaranteed
                #    (ALTER to NOT NULL should be a migration step)
                nullable_fragment = "NULL"  # safe during initial add
                default_fragment = ""
                server_default = getattr(column, "server_default", None)
                if server_default is not None and getattr(server_default, "arg", None) is not None:
                    default_fragment = f"DEFAULT {server_default.arg}"

                add_stmt = f'ALTER TABLE "{table_name}" ADD COLUMN "{column.name}" {sql_type} {nullable_fragment} {default_fragment};'

                try:
                    logger.info(f"Adding missing column `{table_name}.{column.name}` ({sql_type})")
                    conn.execute(text(add_stmt))
                except Exception as e:
                    logger.error(f"Failed to add column `{table_name}.{column.name}`: {e}")
                    continue

                # Optionally enforce NOT NULL if it's safe and requested by model
                if column.nullable is False and _can_add_not_null_without_default(column):
                    try:
                        logger.info(f"Enforcing NOT NULL on `{table_name}.{column.name}`")
                        # Postgres / SQLite syntax for setting NOT NULL differs slightly.
                        # Use a generic ALTER COLUMN if supported; SQLite has limited support.
                        if url.startswith("postgresql"):
                            conn.execute(
                                text(f'ALTER TABLE "{table_name}" ALTER COLUMN "{column.name}" SET NOT NULL;')
                            )
                        elif url.startswith("sqlite"):
                            # SQLite cannot ALTER COLUMN SET NOT NULL directly.
                            # This would require table rebuild; we log instruction instead.
                            logger.warning(
                                f"SQLite cannot enforce NOT NULL via ALTER for `{table_name}.{column.name}`. "
                                f"Use a migration to rebuild the table if required."
                            )
                        else:
                            # Generic fallback; may fail depending on dialect
                            conn.execute(
                                text(f'ALTER TABLE "{table_name}" ALTER COLUMN "{column.name}" SET NOT NULL;')
                            )
                    except Exception as e:
                        logger.warning(
                            f"Could not enforce NOT NULL for `{table_name}.{column.name}` automatically: {e}. "
                            f"Create an Alembic migration if NOT NULL is required."
                        )

    logger.info("Database initialization complete.")
