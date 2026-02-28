# filename: app/core/settings.py
import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Base App Settings
    APP_NAME: str = "ReviewSaaS"
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./review_saas.db")
    DATABASE_PUBLIC_URL: str = ""  # Added to fix validation error
    APP_BASE_URL: str = os.getenv("APP_BASE_URL", "http://localhost:8080")
    SECRET_KEY: str = os.getenv("SECRET_KEY", "your-super-secret-key")

    # Auth & JWT Settings (Required by your environment)
    JWT_SECRET: str = "supersecret256bitkeyhere"
    JWT_ALG: str = "HS256"
    ACCESS_TOKEN_MIN: int = 120
    RESET_TOKEN_MINUTES: int = 30
    VERIFY_TOKEN_HOURS: int = 24
    PASSLIB_MAX_PASSWORD_SIZE: int = 1024
    
    # Cookie & Domain Settings
    COOKIE_DOMAIN: str = ""
    COOKIE_SECURE: bool = False
    
    # Google OAuth & API Keys (Requirement #15)
    OAUTH_GOOGLE_CLIENT_ID: str = os.getenv("GOOGLE_CLIENT_ID", "")
    OAUTH_GOOGLE_CLIENT_SECRET: str = os.getenv("GOOGLE_CLIENT_SECRET", "")
    OAUTH_GOOGLE_REDIRECT_URI: str = ""
    GOOGLE_BUSINESS_API_KEY: str = ""
    GOOGLE_MAPS_API_KEY: str = ""
    GOOGLE_PLACES_API_KEY: str = ""

    # SMTP / Email Settings
    SMTP_HOST: str = "localhost"
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = ""
    SMTP_FROM_NAME: str = "Review SaaS"
    
    # Auth Security Logic
    LOCKOUT_THRESHOLD: int = 5
    LOCKOUT_MINUTES: int = 15

    # Requirement: Allow extra environment variables without crashing
    model_config = SettingsConfigDict(
        env_file=".env", 
        extra="ignore"  # This prevents the "Extra inputs" error in the future
    )

settings = Settings()
