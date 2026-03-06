# File: review_saas/app/core/config.py
import os
from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    # --- App General Settings ---
    APP_NAME: str = "Sentiment-Analysis-SaaS"
    # ... other settings ...

    # --- Scraping Settings ---
    OUTSCAPTER_KEY: str # Make sure this matches your .env exactly
    
    # --- Database Settings ---
    # THIS LINE WAS LIKELY MISSING OR RENAMED:
    DATABASE_URL: str 

    # --- Google OAuth & API Settings ---
    GOOGLE_CLIENT_ID: str
    GOOGLE_CLIENT_SECRET: str
    GOOGLE_REFRESH_TOKEN: str
    GOOGLE_REDIRECT_URI: str
    GOOGLE_PLACES_API_KEY: str

    # ... rest of your settings (SECRET_KEY, etc.) ...

    class Config:
        case_sensitive = True
        env_file = ".env"
        extra = "ignore"

settings = Settings()
