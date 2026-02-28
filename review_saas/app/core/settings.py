# File: app/core/settings.py
from __future__ import annotations
from typing import Optional
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # App
    APP_NAME: str = "ReviewSaaS"
    SECRET_KEY: str = "dev-secret"  # Set via env in production

    # Database
    DATABASE_URL: Optional[str] = None  # e.g., postgresql+psycopg://user:pass@host:5432/db

    # Google
    GOOGLE_MAPS_API_KEY: Optional[str] = None
    GOOGLE_SERVICE_ACCOUNT_FILE: Optional[str] = None
    GOOGLE_SCOPES: Optional[str] = None  # comma-separated overrides

    class Config:
        env_file = ".env"
        case_sensitive = False

settings = Settings()
