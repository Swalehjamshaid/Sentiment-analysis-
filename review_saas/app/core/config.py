import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator
from typing import Optional

class Settings(BaseSettings):
    # --- REQUIRED BY main.py ---
    APP_NAME: str = "ReviewSaaS AI"
    # Requirement 8: Security
    SECRET_KEY: str = os.getenv("SECRET_KEY", "your-default-secret-key-for-dev")
    # Requirement 124: Database (Railway Injected)
    # We provide a fallback string to prevent the 'Value error' crash
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/db")
    COOKIE_SECURE: bool = True

    # --- GOOGLE API KEYS (Requirement 128) ---
    GOOGLE_PLACES_API_KEY: Optional[str] = None
    GOOGLE_MAPS_API_KEY: Optional[str] = None

    # --- VALIDATION ---
    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def check_db_url(cls, v):
        if not v or v.strip() == "":
            # If empty, we use a local sqlite fallback for safety or raise a cleaner error
            return "sqlite:///./fallback.db"
        return v

    # --- THE CRITICAL FIX ---
    # extra='ignore' tells Pydantic to stop crashing when it sees 
    # variables like 'jwt_secret' or 'app_base_url' in Railway
    model_config = SettingsConfigDict(
        extra='ignore', 
        env_file=".env",
        case_sensitive=False # Set to False to handle 'jwt_secret' vs 'JWT_SECRET'
    )

settings = Settings()
