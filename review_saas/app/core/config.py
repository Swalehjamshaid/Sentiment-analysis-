
from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    # App
    APP_NAME: str = "Review SaaS Pro"

    # Secrets / DB
    SECRET_KEY: str = "change-me"
    DATABASE_URL: str = "sqlite:///./app.db"

    # Security / Auth
    FORCE_HTTPS: int = 0
    TOKEN_MINUTES: int = 60
    ENABLE_2FA: int = 0

    # OAuth (optional)
    GOOGLE_CLIENT_ID: Optional[str] = None
    GOOGLE_CLIENT_SECRET: Optional[str] = None
    OAUTH_REDIRECT_URL: Optional[str] = None

    # Google APIs
    GOOGLE_MAPS_API_KEY: Optional[str] = None
    GOOGLE_PLACES_API_KEY: Optional[str] = None
    # Backwards compat
    GOOGLE_API_KEY: Optional[str] = None

    # Email / SMTP
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASS: Optional[str] = None
    FROM_EMAIL: str = "no-reply@example.com"

    # Scheduler (optional)
    ENABLE_SCHEDULER: int = 0
    FETCH_CRON: str = "0 0 * * *"

    # Alerts (optional)
    ENABLE_ALERTS: int = 0
    NEGATIVE_ALERT_THRESHOLD: int = 1

    # PDF (optional)
    REPORT_LOGO_URL: Optional[str] = None

    class Config:
        env_file = ".env"

settings = Settings()
