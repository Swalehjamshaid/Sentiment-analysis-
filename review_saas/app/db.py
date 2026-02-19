# Filename: app/db.py
import logging
from sqlalchemy import create_engine, inspect, Column
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import OperationalError
from .core.config import settings
from .models import Base
import sqlalchemy

logger = logging.getLogger(__name__)

# -----------------------------
# DATABASE URL CONFIGURATION
# -----------------------------
url = settings.DATABASE_URL or "sqlite:///./app.db"

if url.startswith("postgres://"):
    url = url.replace("postgres://", "postgresql://", 1)

if url.startswith("postgresql://") and "+psycopg" not in url:
    url = url.replace("postgresql://", "postgresql+psycopg://", 1)

if url.startswith("postgresql+psycopg://") and "sslmode" not in url:
    sep = "&" if "?" in url else "?"
    url = f"{url}{sep}sslmode=require"

logger.info(f"Using database URL: {url}")

# -----------------------------
# SQLALCHEMY ENGINE
# -----------------------------
engine = create_engine(
    url,
    future=True,
    echo=False,
    connect_args={"check_same_thread": False} if url.startswith("sqlite") else {},
    pool_pre_ping=True,
)

# -----------------------------
# SESSION FACTORY
# -----------------------------
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    future=True,
)

# -----------------------------
# FASTAPI DEPENDENCY
# -----------------------------
def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# -----------------------------
# FLEXIBLE AUTO-UPGRADE
# -----------------------------
def auto_upgrade_db():
    """
    Automatically create missing tables and columns based on models.py
    Will not drop existing tables or data.
    """
    inspector = inspect(engine)
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            table_name = table.name
            if not inspector.has_table(table_name):
                logger.info(f"Creating missing table: {table_name}")
                table.create(bind=engine)
            else:
                # Check columns
                existing_columns = [col['name'] for col in inspector.get_columns(table_name)]
                for col in table.columns:
                    if col.name not in existing_columns:
                        try:
                            ddl = sqlalchemy.schema.AddColumn(col).compile(engine)
                            conn.execute(sqlalchemy.text(str(ddl)))
                            logger.info(f"Added new column '{col.name}' to table '{table_name}'")
                        except Exception as e:
                            logger.error(f"Failed to add column '{col.name}' to '{table_name}': {e}")
    logger.info("Database auto-upgrade completed.")

# -----------------------------
# RUN AUTO-UPGRADE ON STARTUP
# -----------------------------
auto_upgrade_db()
