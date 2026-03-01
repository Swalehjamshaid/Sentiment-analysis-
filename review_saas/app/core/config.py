# filename: app/core/config.py

from __future__ import annotations

from functools import lru_cache
from typing import List, Optional

from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Central application configuration (Pydantic v2 + pydantic-settings).
    Reads from environment variables and .env by default.
    """

    # --- App ---
    APP_NAME: str = "ReviewSaaS"
    DEBUG: bool = False
    ENV: str = Field(default="production", description="environment: development|staging|production")
    SECRET_KEY: str = Field(default="change-me", description="Cryptographic secret")

    # --- Server ---
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # --- CORS / URLs ---
    BACKEND_CORS_ORIGINS: List[AnyHttpUrl] = []
    BASE_URL: Optional[AnyHttpUrl] = None

    # --- Database ---
    # Keep as Optional to allow startup even if not set (you can validate later at DB init)
    DATABASE_URL: Optional[str] = None
    DATABASE_PUBLIC_URL: Optional[str] = None

    # --- Google APIs ---
    GOOGLE_MAPS_API_KEY: Optional[str] = None
    GOOGLE_PLACES_API_KEY: Optional[str] = None
    GOOGLE_BUSINESS_API_KEY: Optional[str] = None

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
        extra="ignore",  # ignore unknown env vars instead of raising
    )

    @property
    def EFFECTIVE_DATABASE_URL(self) -> str:
        """
        Prefer DATABASE_URL; fall back to DATABASE_PUBLIC_URL if provided.
        Returns empty string if neither is set (so callers can validate explicitly).
        """
        return (self.DATABASE_URL or self.DATABASE_PUBLIC_URL or "").strip()


@lru_cache
def get_settings() -> Settings:
    """
    Cached accessor to avoid re-parsing the env on each import.
    """
    return Settings()


# ✅ Export a module-level 'settings' for legacy imports:
settings: Settings = get_settings()

__all__ = ["Settings", "get_settings", "settings"]
