import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    # --- Existing REQUIRED by main.py ---
    APP_NAME: str = "ReviewSaaS AI"
    SECRET_KEY: str = os.getenv("SECRET_KEY", "your-secret-key-here")
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")
    COOKIE_SECURE: bool = True
    
    # --- Missing Fields (Fixes the "Extra inputs" error) ---
    # These must match the names in your error log exactly
    JWT_SECRET: str = "supersecret256bitkeyhere"
    JWT_ALG: str = "HS256"
    ACCESS_TOKEN_MIN: int = 120
    APP_BASE_URL: str = ""
    COOKIE_DOMAIN: str = ".up.railway.app"
    
    # Google API Keys
    GOOGLE_BUSINESS_API_KEY: Optional[str] = None
    GOOGLE_MAPS_API_KEY: Optional[str] = None
    GOOGLE_PLACES_API_KEY: Optional[str] = None
    
    # OAuth
    OAUTH_GOOGLE_CLIENT_ID: Optional[str] = None
    OAUTH_GOOGLE_CLIENT_SECRET: Optional[str] = None
    OAUTH_GOOGLE_REDIRECT_URI: Optional[str] = None
    
    # Security & Lockout
    LOCKOUT_THRESHOLD: int = 5
    LOCKOUT_MINUTES: int = 15
    PASSLIB_MAX_PASSWORD_SIZE: int = 1024
    
    # Email / Tokens
    RESET_TOKEN_MINUTES: int = 30
    VERIFY_TOKEN_HOURS: int = 24
    SMTP_USERNAME: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_FROM_NAME: str = "Review SaaS"
    SMTP_FROM_EMAIL: Optional[str] = None

    # --- THE CRITICAL FIX ---
    # This tells Pydantic to allow extra variables in your .env/Environment
    # without crashing the app.
    model_config = SettingsConfigDict(
        extra='ignore',  # This ignores any variable not defined above
        env_file=".env",
        case_sensitive=True
    )

settings = Settings()
