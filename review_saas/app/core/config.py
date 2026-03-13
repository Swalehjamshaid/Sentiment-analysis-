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
    OUTSCRAPER_API_KEY: Optional[str] = None
    OUTSCAPTER_KEY: Optional[str] = None  # Legacy fallback
    
    # --- Database Settings ---
    DATABASE_URL: str

    # --- Google OAuth & API Settings ---
    GOOGLE_CLIENT_ID: str
    GOOGLE_CLIENT_SECRET: str
    GOOGLE_REFRESH_TOKEN: str
    GOOGLE_REDIRECT_URI: str = "https://sentiment-analysis-production-f96a.up.railway.app/auth/callback"

    # Your original variable (KEEPING IT)
    GOOGLE_PLACES_API_KEY: Optional[str] = None  

    # Added for backend compatibility (NEW)
    GOOGLE_MAPS_API_KEY: Optional[str] = None  

    # --- Rate Limiting Settings ---
    RATE_LIMIT_WINDOW_SEC: int = 60
    RATE_LIMIT_REQUESTS: int = 100  

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

    # --- Helper: unified Google key resolver ---
    @property
    def GOOGLE_API_KEY(self) -> str:
        """
        Ensures ANY of the following environment variables will work:
            GOOGLE_MAPS_API_KEY  (recommended)
            GOOGLE_PLACES_API_KEY  (your existing)
        """
        return (
            self.GOOGLE_MAPS_API_KEY
            or self.GOOGLE_PLACES_API_KEY
            or ""
        )

settings = Settings()
