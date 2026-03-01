# filename: app/core/db.py
from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine
from sqlalchemy.exc import SQLAlchemyError
from app.core.config import settings
import sys

try:
    if not settings.DATABASE_URL:
        raise RuntimeError("DATABASE_URL is empty. Please set it in your .env file.")

    engine: AsyncEngine = create_async_engine(
        settings.DATABASE_URL,
        echo=settings.DEBUG,
        future=True,
    )

except SQLAlchemyError as e:
    raise RuntimeError(f"Could not create SQLAlchemy engine: {e}") from e
except RuntimeError as e:
    print(e)
    sys.exit(1)
