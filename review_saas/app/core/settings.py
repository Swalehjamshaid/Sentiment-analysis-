
# filename: app/core/settings.py
from __future__ import annotations
from pydantic_settings import BaseSettings
from pydantic import AnyHttpUrl, Field
from typing import Optional

class Settings(BaseSettings):
    APP_NAME: str = 'ReviewSaaS'
    APP_BASE_URL: Optional[AnyHttpUrl] = None
    COOKIE_DOMAIN: Optional[str] = None
    COOKIE_SECURE: bool = True

    DATABASE_URL: str = 'sqlite:///./app.db'
    DATABASE_PUBLIC_URL: Optional[str] = None

    JWT_SECRET: str = 'change_me'
    JWT_ALG: str = 'HS256'
    ACCESS_TOKEN_MIN: int = 120

    VERIFY_TOKEN_HOURS: int = 24
    RESET_TOKEN_MINUTES: int = 30
    LOCKOUT_THRESHOLD: int = 5
    LOCKOUT_MINUTES: int = 15

    GOOGLE_MAPS_API_KEY: str = ''
    GOOGLE_PLACES_API_KEY: str = ''
    GOOGLE_BUSINESS_API_KEY: str = ''

    OAUTH_GOOGLE_CLIENT_ID: Optional[str] = None
    OAUTH_GOOGLE_CLIENT_SECRET: Optional[str] = None
    OAUTH_GOOGLE_REDIRECT_URI: Optional[str] = None

    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_USERNAME: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_FROM_EMAIL: Optional[str] = None
    SMTP_FROM_NAME: str = 'Reputation SaaS'

    PASSLIB_MAX_PASSWORD_SIZE: int = 1024

    class Config:
        env_file = '.env'
        extra = 'allow'

settings = Settings()
