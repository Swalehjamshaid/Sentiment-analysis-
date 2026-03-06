# File: review_saas/app/core/config.py
import os
from pydantic_settings import BaseSettings
from typing import Optional

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
    GOOGLE_PLACES_API_KEY: str
    
    # --- Rate Limiting Settings (FIXES THE CURRENT ERROR) ---
    RATE_LIMIT_WINDOW_SEC: int = 60
    RATE_LIMIT_MAX_REQUESTS: int = 5

    # --- Database Settings ---
    DATABASE_URL: str

    # --- Security & JWT Settings ---
    SECRET_KEY: str
    JWT_SECRET: str
    JWT_ALG: str = "HS256"
    ACCESS_TOKEN_MINUTES: int = 60

    # --- Email / SMTP Settings ---
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USERNAME: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None

    class Config:
        case_sensitive = True
        env_file = ".env"
        # Ignores extra variables in Railway dashboard to prevent crashes
        extra = "ignore"

settings = Settings()
