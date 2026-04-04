import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, AliasChoices, model_validator

class Settings(BaseSettings):
    """
    100% Complete Configuration for Review Intel AI.
    Optimized for Python 3.12 and Pydantic V2.
    """
    APP_NAME: str = "Review-Intel-AI"
    # Use .get() with defaults for all OS envs to prevent 'NoneType' crashes
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "production")
    DEBUG: bool = os.getenv("DEBUG", "False").lower() in ("true", "1", "t")
    
    # Railway/Production URL
    APP_BASE_URL: str = os.getenv("APP_BASE_URL", "https://sentiment-analysis-production-f96a.up.railway.app")
    
    # Database Settings - Critical: use a string for the default
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./test.db")
    
    # Security & Sessions
    SECRET_KEY: str = os.getenv("SECRET_KEY", "super-secret-key-jamshaid-2026")
    SESSION_COOKIE_NAME: str = "session"
    
    # SMTP / Email Settings
    MAIL_USERNAME: str = os.getenv("MAIL_USERNAME", "roy.jamshaid@gmail.com")
    MAIL_PASSWORD: str = os.getenv("MAIL_PASSWORD", "")
    MAIL_FROM: str = os.getenv("MAIL_FROM", "noreply@reviewintel.ai")
    MAIL_PORT: int = int(os.getenv("MAIL_PORT", "587")) # String wrap for safety
    MAIL_SERVER: str = os.getenv("MAIL_SERVER", "smtp.gmail.com")

    # API Keys
    GOOGLE_API_KEY: str = os.getenv("GOOGLE_API_KEY", "")
    GOOGLE_MAPS_API_KEY: Optional[str] = os.getenv("GOOGLE_MAPS_API_KEY")
    
    # Scraper Keys
    SERPAPI_KEY: str = os.getenv("SERPAPI_KEY", "f9f41e452ea716ca1e760081b94763a404c9e1e07aef30def9c6a05391890e8d")
    OUTSCRAPER_API_KEY: Optional[str] = os.getenv("OUTSCRAPER_API_KEY")

    # Pydantic Configuration
    model_config = SettingsConfigDict(
        env_file=".env", 
        extra="ignore", 
        case_sensitive=False # Set to False to prevent 'APP_NAME' vs 'app_name' alignment issues
    )

    @model_validator(mode="after")
    def _normalize_keys(self) -> "Settings":
        """Ensures API keys are cross-populated if one is missing."""
        key = self.GOOGLE_MAPS_API_KEY or self.GOOGLE_API_KEY
        if key:
            self.GOOGLE_API_KEY = key
            self.GOOGLE_MAPS_API_KEY = key
        return self

# --- THE FIX FOR ALIGNMENT ---
# We use a function to get settings, or initialize carefully.
# This prevents the circular import 'deadlock'.
settings = Settings()
