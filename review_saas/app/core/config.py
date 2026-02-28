# filename: app/core/config.py
from pydantic_settings import BaseSettings
from pydantic import EmailStr, Field
from typing import Optional

class Settings(BaseSettings):
    ACCESS_TOKEN_MIN: int = 120
    APP_BASE_URL: str = "http://localhost:8000"
    COOKIE_DOMAIN: str = "localhost"
    COOKIE_SECURE: bool = False

    DATABASE_URL: str = "sqlite:///./app.db"

    JWT_ALG: str = "HS256"
    JWT_SECRET: str = "change_me"

    LOCKOUT_MINUTES: int = 15
    LOCKOUT_THRESHOLD: int = 5

    OAUTH_GOOGLE_CLIENT_ID: Optional[str] = None
    OAUTH_GOOGLE_CLIENT_SECRET: Optional[str] = None
    OAUTH_GOOGLE_REDIRECT_URI: Optional[str] = None

    RESET_TOKEN_MINUTES: int = 30
    VERIFY_TOKEN_HOURS: int = 24

    SMTP_FROM_EMAIL: EmailStr = "noreply@example.com"
    SMTP_FROM_NAME: str = "Review SaaS"
    SMTP_HOST: str = "localhost"
    SMTP_PASSWORD: str = ""
    SMTP_PORT: int = 1025
    SMTP_USERNAME: Optional[str] = None

    GOOGLE_MAPS_API_KEY: Optional[str] = None

    class Config:
        env_file = ".env"

settings = Settings()
