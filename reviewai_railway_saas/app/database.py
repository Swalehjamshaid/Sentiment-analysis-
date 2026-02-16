from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite+aiosqlite:///./data.db"
    SECRET_KEY: str = "change-this"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60*24*30
    GOOGLE_MAPS_API_KEY: str | None = None
    COMPANY_CONTACT_EMAIL: str = "support@example.com"
    COMPANY_CONTACT_PHONE: str = "+92-300-0000000"
    APP_NAME: str = "Review Management & AI Response SaaS"

    class Config:
        env_file = ".env"

settings = Settings()

engine = create_async_engine(settings.DATABASE_URL, echo=False, future=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)
Base = declarative_base()