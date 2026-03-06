import os
from pydantic_settings import BaseSettings
from typing import Optional, List

class Settings(BaseSettings):
    # --- App General Settings ---
    APP_NAME: str = "Sentiment-Analysis-SaaS"
    ENVIRONMENT: str = "production"
    DEBUG: bool = False
    APP_BASE_URL: str = "https://sentiment-analysis-production-f96a.up.railway.app"
    
    # --- Google OAuth & API Settings ---
    GOOGLE_CLIENT_ID: str
    GOOGLE_CLIENT_SECRET: str
    GOOGLE_REFRESH_TOKEN: str
    GOOGLE_REDIRECT_URI: str = "https://sentiment-analysis-production-f96a.up.railway.app/auth/callback"
    
    # Google API Keys
    GOOGLE_PLACES_API_KEY: str
    GOOGLE_MAPS_API_KEY: Optional[str] = None
    
    # --- Database Settings ---
    DATABASE_URL: str

    # --- Security & JWT Settings ---
    SECRET_KEY: str
    JWT_SECRET: str
    JWT_ALG: str = "HS256"
    ACCESS_TOKEN_MINUTES: int = 60

    # --- Session & Cookie Settings ---
    SESSION_COOKIE_NAME: str = "session"
    SESSION_COOKIE_SAMESITE: str = "lax"
    SESSION_COOKIE_SECURE: bool = True

    # --- Email / SMTP Settings ---
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USERNAME: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_FROM_NAME: str = "ReviewSaaS-Support"
    SMTP_FROM_EMAIL: Optional[str] = None

    # --- Third Party APIs ---
    SERPAPI_KEY: Optional[str] = None
    OUTSCRAPER_API_KEY: Optional[str] = None

    class Config:
        case_sensitive = True
        env_file = ".env"
        # CRITICAL FIX: This prevents "Extra inputs are not permitted" crashes
        # if Railway has variables like GOOGLE_BUSINESS_API_KEY or FORCE_HTTPS
        extra = "ignore"

# Initialize settings object to be used across the app
settings = Settings()
