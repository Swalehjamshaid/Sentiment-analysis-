import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

# 1. Get the URL from environment variables
DATABASE_URL = os.getenv("DATABASE_URL")

# 2. FAIL-SAFE: Auto-correct the URL prefix for Async compatibility
if DATABASE_URL:
    # Handle 'postgres://' (Common in Railway/Heroku)
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)
    # Handle 'postgresql://' (The SQLAlchemy default)
    elif DATABASE_URL.startswith("postgresql://") and "+asyncpg" not in DATABASE_URL:
        DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

# 3. Create the Async Engine
# We use the 'postgresql+asyncpg' dialect to avoid the psycopg2 error
engine = create_async_engine(
    DATABASE_URL,
    echo=True,       # Set to False in production to reduce log noise
    future=True,
    pool_size=10,
    max_overflow=20
)

# 4. Create the Session Factory
async_session = async_sessionmaker(
    engine, 
    expire_on_commit=False, 
    class_=AsyncSession
)

# 5. Base class for models
class Base(DeclarativeBase):
    pass

# 6. Dependency for FastAPI routes
async def get_session():
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()
