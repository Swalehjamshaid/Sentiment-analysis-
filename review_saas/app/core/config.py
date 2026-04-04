# filename: app/core/config.py
from __future__ import annotations
import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, AliasChoices, model_validator

class Settings(BaseSettings):
    # --- App General Settings ---
    APP_NAME: str = "Sentiment-Analysis-SaaS"
    ENVIRONMENT: str = "production"
    DEBUG: bool = False
    APP_BASE_URL: str = "https://sentiment-analysis-production-f96a.up.railway.app"

    # --- Scraping Settings ---
    OUTSCRAPER_API_KEY: Optional[str] = None
    OUTSCAPTER_KEY: Optional[str] = None
    OUTSCRAPER_BASE_URL: str = "https://api.outscraper.com"

    # --- Database Settings ---
    DATABASE_URL: str = Field(default="sqlite+aiosqlite:///./test.db")

    # --- Google OAuth & API Settings ---
    GOOGLE_CLIENT_ID: str = "dummy_client_id"
    GOOGLE_CLIENT_SECRET: str = "dummy_client_secret"
    GOOGLE_REFRESH_TOKEN: str = "dummy_refresh_token"
    GOOGLE_REDIRECT_URI: str = "https://sentiment-analysis-production-f96a.up.railway.app/auth/callback"

    # Standard field for use in main.py
    GOOGLE_API_KEY: str = ""
    
    GOOGLE_MAPS_API_KEY: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("GOOGLE_MAPS_API_KEY", "GOOGLE_PLACES_API_KEY", "GOOGLE_API_KEY"),
    )
    GOOGLE_PLACES_API_KEY: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("GOOGLE_PLACES_API_KEY", "GOOGLE_MAPS_API_KEY", "GOOGLE_API_KEY"),
    )

    # --- Rate Limiting Settings ---
    RATE_LIMIT_WINDOW_SEC: int = 60
    RATE_LIMIT_REQUESTS: int = 100

    # --- Session & Cookie Settings ---
    SESSION_COOKIE_NAME: str = "session"
    SESSION_COOKIE_SAMESITE: str = "lax"
    SESSION_COOKIE_SECURE: bool = True

    # --- Security & JWT Settings ---
    SECRET_KEY: str = "supersecretkey"
    JWT_SECRET: str = "supersecretjwt"
    JWT_ALG: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # --- Email / SMTP Settings ---
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USERNAME: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_FROM_EMAIL: Optional[str] = None

    # Pydantic V2 Configuration
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True
    )

    @model_validator(mode="after")
    def _normalize_google_keys(self) -> "Settings":
        # Check all possible sources for the key
        key = self.GOOGLE_MAPS_API_KEY or self.GOOGLE_PLACES_API_KEY or self.GOOGLE_API_KEY
        if key:
            self.GOOGLE_MAPS_API_KEY = key
            self.GOOGLE_PLACES_API_KEY = key
            self.GOOGLE_API_KEY = key
        return self

# --- Initialize Settings ---
settings = Settings()
