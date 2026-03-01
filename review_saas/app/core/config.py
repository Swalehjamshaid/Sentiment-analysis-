
# filename: app/core/config.py
from __future__ import annotations
from functools import lru_cache
from typing import List, Optional
from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings (Pydantic v2 + pydantic-settings)."""

    # App
    APP_NAME: str = "ReviewSaaS"
    DEBUG: bool = False
    ENV: str = Field(default="production")
    SECRET_KEY: str = Field(default="change-me")

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # URLs / CORS
    BACKEND_CORS_ORIGINS: List[AnyHttpUrl] = []
    BASE_URL: Optional[AnyHttpUrl] = None

    # Database
    DATABASE_URL: Optional[str] = None
    DATABASE_PUBLIC_URL: Optional[str] = None

    # Google APIs
    GOOGLE_MAPS_API_KEY: Optional[str] = None
    GOOGLE_PLACES_API_KEY: Optional[str] = None
    GOOGLE_BUSINESS_API_KEY: Optional[str] = None

    # Feature flags
    ENABLE_GOOGLE_SYNC: bool = True
    ENABLE_SENTIMENT_PIPELINE: bool = True

    # Security / Auth
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24
    SESSION_COOKIE_NAME: str = "session"
    SESSION_COOKIE_SECURE: bool = True
    SESSION_COOKIE_SAMESITE: str = "lax"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
