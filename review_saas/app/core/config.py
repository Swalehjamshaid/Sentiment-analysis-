# filename: app/core/config.py
from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    # App General Settings
    APP_NAME: str = "Sentiment-Analysis-SaaS"
    ENVIRONMENT: str = "production"
    DEBUG: bool = False
    APP_BASE_URL: str = "https://sentiment-analysis-production-f96a.up.railway.app"

    # Google OAuth & API Settings
    GOOGLE_CLIENT_ID: str
    GOOGLE_CLIENT_SECRET: str
    # THIS IS THE MISSING LINE FIXING YOUR ERROR:
    GOOGLE_REFRESH_TOKEN: str 
    
    GOOGLE_REDIRECT_URI: str = "https://sentiment-analysis-production-f96a.up.railway.app/auth/callback"
    GOOGLE_PLACES_API_KEY: str
    GOOGLE_MAPS_API_KEY: Optional[str] = None

    # Database Settings
    DATABASE_URL: str

    # Security Settings
    SECRET_KEY: str
    JWT_SECRET: str
    JWT_ALG: str = "HS256"
    ACCESS_TOKEN_MINUTES: int = 60

    # Email / SMTP Settings
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USERNAME: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_FROM_NAME: str = "ReviewSaaS-Support"
    SMTP_FROM_EMAIL: Optional[str] = None

    class Config:
        case_sensitive = True
        # This allows the app to read from a .env file locally 
        # and environment variables on Railway
        env_file = ".env"

# Initialize settings
settings = Settings()
