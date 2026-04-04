# filename: app/core/db.py
import os
import logging
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    async_sessionmaker,
    AsyncEngine
)
from sqlalchemy.orm import declarative_base

# --------------------------
# 1️⃣ Logging Setup
# --------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --------------------------
# 2️⃣ DATABASE URL
# --------------------------
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is not set!")

# Railway often gives "postgres://", Async SQLAlchemy needs "postgresql+asyncpg://"
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)

# --------------------------
# 3️⃣ ASYNC ENGINE
# --------------------------
engine: AsyncEngine = create_async_engine(
    DATABASE_URL,
    echo=False,
    future=True,
    pool_pre_ping=True,
    connect_args={
        "timeout": 30,          # total timeout
        "command_timeout": 30   # per-command timeout for asyncpg
    }
)

# --------------------------
# 4️⃣ SESSION MAKER
# --------------------------
SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False
)

# --------------------------
# 5️⃣ BASE CLASS
# --------------------------
Base = declarative_base()

# --------------------------
# 6️⃣ FASTAPI SESSION DEPENDENCY
# --------------------------
async def get_session() -> AsyncSession:
    """Dependency for FastAPI routes to get a DB session."""
    async with SessionLocal() as session:
        yield session

# --------------------------
# 7️⃣ INIT MODELS FUNCTION
# --------------------------
async def init_models():
    """Create all tables on startup safely."""
    try:
        # Import models inside the function to prevent circular imports
        from app.core import models  # ensure your models inherit from Base

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("✅ Database alignment complete: Tables created.")
    except Exception as e:
        logger.error(f"❌ Database alignment failed: {e}")
        raise  # Re-raise to fail app startup if DB alignment fails
