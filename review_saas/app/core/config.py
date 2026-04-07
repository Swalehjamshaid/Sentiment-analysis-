# filename: review_saas/app/core/config.py
import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import model_validator

class Settings(BaseSettings):
    """
    100% Complete Configuration for Review Intel AI.
    Optimized for Python 3.12 and Pydantic V2.
    Ensures zero 'NoneType' crashes during boot.
    Includes Absolute Path Resolution for Jinja2 Templates.
    """
    APP_NAME: str = "Review-Intel-AI"
    
    # Environment & Debugging
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "production")
    DEBUG: bool = os.getenv("DEBUG", "False").lower() in ("true", "1", "t")
    
    # --- PATH ALIGNMENT ---
    # Calculates the absolute path to the 'app' directory (parent of 'core')
    # This prevents Jinja2 from failing to find templates in production
    BASE_DIR: str = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    TEMPLATES_DIR: str = os.path.join(BASE_DIR, "templates")
    STATIC_DIR: str = os.path.join(BASE_DIR, "static")

    # Railway/Production URL Alignment
    APP_BASE_URL: str = os.getenv("APP_BASE_URL", "https://sentiment-analysis-production-f96a.up.railway.app")
    
    # Database Settings
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./test.db")
    
    # Security & Sessions
    SECRET_KEY: str = os.getenv("SECRET_KEY", "super-secret-key-jamshaid-2026")
    SESSION_COOKIE_NAME: str = "session"
    
    # SMTP / Email Settings
    MAIL_USERNAME: str = os.getenv("MAIL_USERNAME", "roy.jamshaid@gmail.com")
    MAIL_PASSWORD: str = os.getenv("MAIL_PASSWORD", "")
    MAIL_FROM: str = os.getenv("MAIL_FROM", "noreply@reviewintel.ai")
    MAIL_PORT: int = int(os.getenv("MAIL_PORT", "587")) 
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
        case_sensitive=False # Prevents 'APP_NAME' vs 'app_name' mismatches
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
# Initialize carefully to prevent circular import 'deadlock'
settings = Settings()
