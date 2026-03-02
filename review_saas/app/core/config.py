
# filename: app/core/config.py
from __future__ import annotations
from functools import lru_cache
from typing import Optional, List
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    APP_NAME: str = "ReviewSaaS"
    DEBUG: bool = True
    SECRET_KEY: str = "change-me"
    JWT_SECRET: str = "change-me-too"
    JWT_ALG: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60*24

    # Async DB URL (postgresql+asyncpg or sqlite+aiosqlite)
    DATABASE_URL: Optional[str] = None

    # Google keys
    GOOGLE_MAPS_API_KEY: Optional[str] = None

    # SMTP (email verification + notifications)
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_USERNAME: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_FROM_EMAIL: Optional[str] = None
    SMTP_FROM_NAME: str = "ReviewSaaS"

    # Sessions
    SESSION_COOKIE_NAME: str = "session"
    SESSION_COOKIE_SECURE: bool = False
    SESSION_COOKIE_SAMESITE: str = "lax"

    # Rate limiting & cache
    RATE_LIMIT_REQUESTS: int = 120  # per 15 minutes window
    RATE_LIMIT_WINDOW_SEC: int = 900
    CACHE_TTL_SEC: int = 300

    # i18n
    DEFAULT_LANG: str = 'en'
    SUPPORTED_LANGS: List[str] = ['en']

    # Branding/SEO
    TAGLINE: str = "Turn reviews into decisions"
    LOGO_URL: str = "/static/logo.svg"
    EXPLAINER_VIDEO_URL: str = "https://www.youtube.com/embed/dQw4w9WgXcQ"

    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', case_sensitive=False, extra='ignore')

@lru_cache
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
