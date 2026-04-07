# filename: review_saas/app/core/config.py
import os
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import model_validator

class Settings(BaseSettings):
    """
    100% Complete Configuration for Review Intel AI.
    Fixed for Railway nested 'review_saas' structure.
    """
    APP_NAME: str = "Review-Intel-AI"
    
    # Environment & Debugging
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "production")
    DEBUG: bool = os.getenv("DEBUG", "False").lower() in ("true", "1", "t")
    
    # --- ROBUST PATH ALIGNMENT ---
    # We define these as empty strings initially so Pydantic doesn't crash,
    # then we fill them with absolute paths in the validator.
    TEMPLATES_DIR: str = ""
    STATIC_DIR: str = ""

    # Railway/Production URL Alignment
    APP_BASE_URL: str = os.getenv("APP_BASE_URL", "https://sentiment-analysis-production-f96a.up.railway.app")
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./test.db")
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
    SERPAPI_KEY: str = os.getenv("SERPAPI_KEY", "f9f41e452ea716ca1e760081b94763a404c9e1e07aef30def9c6a05391890e8d")
    OUTSCRAPER_API_KEY: Optional[str] = os.getenv("OUTSCRAPER_API_KEY")

    model_config = SettingsConfigDict(
        env_file=".env", 
        extra="ignore", 
        case_sensitive=False
    )

    @model_validator(mode="after")
    def _finalize_config(self) -> "Settings":
        # 1. Resolve Paths Dynamically
        current_path = Path(__file__).resolve()
        # core -> app
        base_app_dir = current_path.parent.parent
        
        self.TEMPLATES_DIR = str(base_app_dir / "templates")
        self.STATIC_DIR = str(base_app_dir / "static")

        # 2. Normalize Keys
        key = self.GOOGLE_MAPS_API_KEY or self.GOOGLE_API_KEY
        if key:
            self.GOOGLE_API_KEY = key
            self.GOOGLE_MAPS_API_KEY = key
        return self

# Initialize
settings = Settings()
