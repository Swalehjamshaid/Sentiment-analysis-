import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    # Requirement 122: App Metadata
    APP_NAME: str = "ReviewSaaS AI"
    DEBUG: bool = os.getenv("DEBUG", "False").lower() in ("true", "1", "t")
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    
    # Requirement 124: Database Configuration
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./fallback.db")
    
    # Requirement 8: Security
    SECRET_KEY: str = os.getenv("SECRET_KEY", "lahore-secret-key-2026")
    COOKIE_SECURE: bool = ENVIRONMENT == "production"

    # Requirements 128: API Keys
    GOOGLE_PLACES_API_KEY: Optional[str] = os.getenv("GOOGLE_PLACES_API_KEY")

    # Requirement 130: Pydantic Configuration
    model_config = SettingsConfigDict(
        extra='ignore',  # Prevents crash on extra Railway env vars
        env_file=".env",
        case_sensitive=True
    )

settings = Settings()
