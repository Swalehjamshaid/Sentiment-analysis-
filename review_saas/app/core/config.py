# filename: app/core/config.py

from functools import lru_cache
from typing import Optional

from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Central application configuration using Pydantic v2 + pydantic-settings.

    Reads from environment variables and `.env` file by default.
    """

    # --- App ---
    APP_NAME: str = "ReviewSaaS"
    DEBUG: bool = False
    ENV: str = Field(default="production", description="ENV=development|staging|production")
    SECRET_KEY: str = Field(default="change-me", description="Cryptographic secret")

    # --- Server ---
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # --- CORS / URLs ---
    BACKEND_CORS_ORIGINS: list[AnyHttpUrl] = []
    BASE_URL: Optional[AnyHttpUrl] = None

    # --- Database ---
    DATABASE_URL: str = Field(
        default="sqlite+aiosqlite:///./app.db",
        description="SQLAlchemy URL, e.g., postgresql+asyncpg://user:pass@host:5432/db",
    )

    # --- Google APIs ---
    GOOGLE_MAPS_API_KEY: Optional[str] = None
    GOOGLE_CLIENT_ID: Optional[str] = None
    GOOGLE_CLIENT_SECRET: Optional[str] = None

    # --- Feature Flags ---
    ENABLE_GOOGLE_SYNC: bool = True
    ENABLE_SENTIMENT_PIPELINE: bool = True

    # --- Security / Auth ---
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24
    SESSION_COOKIE_NAME: str = "session"
    SESSION_COOKIE_SECURE: bool = True
    SESSION_COOKIE_SAMESITE: str = "lax"

    # pydantic-settings configuration
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # Ignore unknown env vars instead of raising
    )


@lru_cache
def get_settings() -> Settings:
    """
    Cached accessor to avoid re-parsing environment variables on each import.
    """
    return Settings()


# Export a singleton-like settings object for convenience imports
settings = get_settings()
