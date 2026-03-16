# filename: app/core/db.py

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import os

# -------------------------------
# Database URL (Postgres example)
# -------------------------------
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://user:password@localhost:5432/mydb"
)

# -------------------------------
# Create Async Engine
# -------------------------------
engine = create_async_engine(
    DATABASE_URL,
    echo=True,  # Optional: logs SQL queries
    future=True,
)

# -------------------------------
# Create Async Session Factory
# -------------------------------
async_session = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# -------------------------------
# Base for Models
# -------------------------------
Base = declarative_base()
