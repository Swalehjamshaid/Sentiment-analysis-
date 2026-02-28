# filename: app/core/settings.py
from __future__ import annotations
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import AnyHttpUrl, Field
from typing import Optional

class Settings(BaseSettings):
    # --- App Info ---
    APP_NAME: str = 'ReviewSaaS'
    APP_BASE_URL: Optional[str] = "http://localhost:8000"
    
    # --- Security & Auth (Points 7, 8, 129) ---
    JWT_SECRET: str = 'f3a8b2c9d1e5f0a7b3c8d2e6f9a0b1c2d3e4f5g6h7i8j9k0'
    JWT_ALG: str = 'HS256'
    ACCESS_TOKEN_MIN: int = 120
    COOKIE_DOMAIN: Optional[str] = None
    COOKIE_SECURE: bool = True
    
    # --- Database (Points 124, 131) ---
    DATABASE_URL: str = 'sqlite:///./app.db'
    DATABASE_PUBLIC_URL: Optional[str] = None

    # --- Policies (Points 3, 10, 11, 12, 32) ---
    VERIFY_TOKEN_HOURS: int = 24
    RESET_TOKEN_MINUTES: int = 30
    LOCKOUT_THRESHOLD: int = 5
    LOCKOUT_MINUTES: int = 15
    PASSLIB_MAX_PASSWORD_SIZE: int = 72 # Bcrypt limit fix

    # --- External APIs (Points 33, 128) ---
    GOOGLE_MAPS_API_KEY: str = ''
    GOOGLE_PLACES_API_KEY: str = ''
    GOOGLE_BUSINESS_API_KEY: str = ''

    # --- OAuth Google (Point 15) ---
    OAUTH_GOOGLE_CLIENT_ID: Optional[str] = None
    OAUTH_GOOGLE_CLIENT_SECRET: Optional[str] = None
    OAUTH_GOOGLE_REDIRECT_URI: Optional[str] = None

    # --- SMTP (Points 5, 12, 119) ---
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_USERNAME: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_FROM_EMAIL: Optional[str] = None
    SMTP_FROM_NAME: str = 'Reputation SaaS'

    model_config = SettingsConfigDict(
        env_file='.env',
        extra='allow',
        env_ignore_empty=True,
        case_sensitive=True
    )

settings = Settings()
