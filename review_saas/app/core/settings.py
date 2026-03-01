# File: app/core/settings.py
from __future__ import annotations
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # --- App Core ---
    APP_NAME: str = "ReviewSaaS"
    SECRET_KEY: str = "dev-secret"
    APP_BASE_URL: Optional[str] = None
    
    # --- Auth & JWT Security ---
    JWT_SECRET: str = "supersecret256bitkeyhere"
    JWT_ALG: str = "HS256"
    ACCESS_TOKEN_MIN: int = 120
    COOKIE_DOMAIN: Optional[str] = None
    COOKIE_SECURE: bool = False
    
    # --- Database ---
    DATABASE_URL: Optional[str] = None
    DATABASE_PUBLIC_URL: Optional[str] = None

    # --- Google Integration Keys ---
    GOOGLE_MAPS_API_KEY: Optional[str] = None
    GOOGLE_PLACES_API_KEY: Optional[str] = None
    GOOGLE_BUSINESS_API_KEY: Optional[str] = None
    GOOGLE_SERVICE_ACCOUNT_FILE: Optional[str] = None
    GOOGLE_SCOPES: Optional[str] = None
    
    # --- Google OAuth Credentials ---
    OAUTH_GOOGLE_CLIENT_ID: Optional[str] = None
    OAUTH_GOOGLE_CLIENT_SECRET: Optional[str] = None
    OAUTH_GOOGLE_REDIRECT_URI: Optional[str] = None

    # --- Email / SMTP ---
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_USERNAME: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    EMAILS_FROM_EMAIL: Optional[str] = None

    # --- Security & Rate Limiting ---
    PASSLIB_MAX_PASSWORD_SIZE: int = 1024
    LOCKOUT_MINUTES: int = 15
    LOCKOUT_THRESHOLD: int = 5
    VERIFY_TOKEN_HOURS: int = 24
    RESET_TOKEN_MINUTES: int = 30

    # --- Pydantic V2 Configuration ---
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore"  # Critical: Ignores extra Railway env vars to prevent crashing
    )

settings = Settings()
