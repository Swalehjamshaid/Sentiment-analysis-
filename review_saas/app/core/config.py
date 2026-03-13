# filename: app/core/config.py

import os
from typing import Optional

from pydantic_settings import BaseSettings
from pydantic import Field, AliasChoices, ValidationError, field_validator, model_validator


class Settings(BaseSettings):
    # --- App General Settings ---
    APP_NAME: str = "Sentiment-Analysis-SaaS"
    ENVIRONMENT: str = "production"
    DEBUG: bool = False
    APP_BASE_URL: str = "https://sentiment-analysis-production-f96a.up.railway.app"

    # --- Scraping Settings ---
    # Fixed Typo: Using OUTSCRAPER_API_KEY as the primary standard
    OUTSCRAPER_API_KEY: Optional[str] = None
    # Fallback to the typo version so existing Railway variables don't break
    OUTSCAPTER_KEY: Optional[str] = None

    # --- Database Settings ---
    DATABASE_URL: str

    # --- Google OAuth & API Settings ---
    GOOGLE_CLIENT_ID: str
    GOOGLE_CLIENT_SECRET: str
    GOOGLE_REFRESH_TOKEN: str
    GOOGLE_REDIRECT_URI: str = "https://sentiment-analysis-production-f96a.up.railway.app/auth/callback"

    # Accept either env var name for Places/Maps key and normalize:
    # - If you set GOOGLE_MAPS_API_KEY in Railway/.env -> it fills BOTH fields
    # - If you set GOOGLE_PLACES_API_KEY in Railway/.env -> it fills BOTH fields
    GOOGLE_MAPS_API_KEY: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("GOOGLE_MAPS_API_KEY", "GOOGLE_PLACES_API_KEY"),
    )
    GOOGLE_PLACES_API_KEY: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("GOOGLE_PLACES_API_KEY", "GOOGLE_MAPS_API_KEY"),
    )

    # --- Rate Limiting Settings ---
    RATE_LIMIT_WINDOW_SEC: int = 60
    RATE_LIMIT_REQUESTS: int = 100  # Increased for production usability

    # --- Session & Cookie Settings ---
    SESSION_COOKIE_NAME: str = "session"
    SESSION_COOKIE_SAMESITE: str = "lax"
    SESSION_COOKIE_SECURE: bool = True

    # --- Security & JWT Settings ---
    SECRET_KEY: str
    JWT_SECRET: str
    JWT_ALG: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # --- Email / SMTP Settings ---
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USERNAME: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_FROM_EMAIL: Optional[str] = None

    # Pydantic settings config
    class Config:
        case_sensitive = True
        env_file = ".env"
        extra = "ignore"

    # ---- Normalization & validation for Google API key ----
    @model_validator(mode="after")
    def _normalize_google_keys(self):
        """
        Ensure that at least one of GOOGLE_MAPS_API_KEY / GOOGLE_PLACES_API_KEY is provided.
        Then mirror the value so both fields are populated. This way, any existing code that
        reads either field continues to work.
        """
        key = self.GOOGLE_MAPS_API_KEY or self.GOOGLE_PLACES_API_KEY
        if not key:
            # You can relax this to a warning if you want to allow boot without the key
            raise ValueError(
                "Missing Google API key. Set either GOOGLE_MAPS_API_KEY or GOOGLE_PLACES_API_KEY "
                "in your environment variables."
            )
        self.GOOGLE_MAPS_API_KEY = key
        self.GOOGLE_PLACES_API_KEY = key
        return self

    @property
    def GOOGLE_API_KEY(self) -> str:
        """
        Convenience accessor for service code that just wants 'the key'.
        Not required by your existing code, but useful going forward.
        """
        return self.GOOGLE_MAPS_API_KEY or self.GOOGLE_PLACES_API_KEY or ""


settings = Settings()
