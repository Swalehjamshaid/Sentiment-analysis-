# filename: app/core/config.py

import os
from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    # --- App General Settings ---
    APP_NAME: str = "Sentiment-Analysis-SaaS"
    ENVIRONMENT: str = "production"
    DEBUG: bool = False
    APP_BASE_URL: str = "https://sentiment-analysis-production-f96a.up.railway.app"
    
    # --- Scraping Settings ---
    # Fixed Typo: Using OUTSCRAPER_API_KEY as the primary standard
    OUTSCRAPER_API_KEY: Optional[str] = None 
    # Fallback to the typo version so existing Railway variables don't break
    OUTSCAPTER_KEY: Optional[str] = None 
    
    # --- Database Settings ---
    DATABASE_URL: str

    # --- Google OAuth & API Settings ---
    GOOGLE_CLIENT_ID: str
    GOOGLE_CLIENT_SECRET: str
    GOOGLE_REFRESH_TOKEN: str
    GOOGLE_REDIRECT_URI: str = "https://sentiment-analysis-production-f96a.up.railway.app/auth/callback"
    GOOGLE_PLACES_API_KEY: str
    
    # --- Rate Limiting Settings ---
    RATE_LIMIT_WINDOW_SEC: int = 60
    RATE_LIMIT_REQUESTS: int = 100 # Increased for production usability 

    # --- Session & Cookie Settings ---
    SESSION_COOKIE_NAME: str = "session"
    SESSION_COOKIE_SAMESITE: str = "lax"
    SESSION_COOKIE_SECURE: bool = True

    # --- Security & JWT Settings ---
    SECRET_KEY: str
    JWT_SECRET: str
    JWT_ALG: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 

    # --- Email / SMTP Settings ---
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USERNAME: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_FROM_EMAIL: Optional[str] = None

    class Config:
        case_sensitive = True
        env_file = ".env"
        extra = "ignore"

settings = Settings()
