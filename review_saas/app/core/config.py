import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    # App Settings
    APP_NAME: str = "ReviewSaaS"
    APP_BASE_URL: str = "https://sentiment-analysis-production-ca50.up.railway.app"
    
    # Requirement 124: Database
    # CRITICAL: This must be a real URL. If "host:port" is present, SQLAlchemy crashes.
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")

    # Requirement 8: Security & JWT
    JWT_SECRET: str = os.getenv("JWT_SECRET", "fallback-secret-for-dev")
    JWT_ALG: str = os.getenv("JWT_ALG", "HS256")
    ACCESS_TOKEN_MIN: int = 120
    
    # Requirement 18: Cookies
    COOKIE_DOMAIN: str = "sentiment-analysis-production-ca50.up.railway.app"
    COOKIE_SECURE: bool = True
    
    # Requirement 128: Google APIs
    GOOGLE_BUSINESS_API_KEY: Optional[str] = None
    GOOGLE_MAPS_API_KEY: Optional[str] = None
    GOOGLE_PLACES_API_KEY: Optional[str] = None
    
    # Requirement 15: OAuth
    OAUTH_GOOGLE_CLIENT_ID: Optional[str] = None
    OAUTH_GOOGLE_CLIENT_SECRET: Optional[str] = None
    OAUTH_GOOGLE_REDIRECT_URI: str = ""

    # Requirement 10: Lockout & Passwords
    LOCKOUT_MINUTES: int = 30
    LOCKOUT_THRESHOLD: int = 5
    PASSLIB_MAX_PASSWORD_SIZE: int = 72

    # Requirement 5: Email & Tokens
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USERNAME: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_FROM_EMAIL: Optional[str] = None
    SMTP_FROM_NAME: str = "ReviewSaaS"
    VERIFY_TOKEN_HOURS: int = 24
    RESET_TOKEN_MINUTES: int = 30

    # Pydantic Config to handle Railway environment
    model_config = SettingsConfigDict(
        extra='ignore', 
        env_file=".env",
        case_sensitive=True
    )

settings = Settings()
