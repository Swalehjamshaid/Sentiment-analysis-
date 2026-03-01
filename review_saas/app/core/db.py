# filename: app/core/reset_db.py
import logging
from sqlalchemy import text
from app.core.db import engine, init_db
from app.models.models import Base

logger = logging.getLogger("app.reset_db")
logging.basicConfig(level=logging.INFO)

def reset_database():
    logger.info("Dropping all existing tables...")
    with engine.connect() as conn:
        # Drop all tables
        conn.execute(text("DROP SCHEMA public CASCADE;"))
        conn.execute(text("CREATE SCHEMA public;"))
        logger.info("Schema reset complete.")

    logger.info("Creating all tables from models...")
    init_db(Base)
    logger.info("✅ Database reset and tables created successfully.")

if __name__ == "__main__":
    reset_database()
