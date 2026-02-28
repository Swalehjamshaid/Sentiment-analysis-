# File: review_saas/app/core/settings.py
import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """
    Complete configuration for ReviewSaaS.
    Pulls live data from environment variables with safe defaults.
    """
    # --- Base App Settings ---
    APP_NAME: str = "ReviewSaaS"
    # Railway provides DATABASE_URL; fallback to persistent SQLite local file
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./review_saas.db")
    DATABASE_PUBLIC_URL: str = os.getenv("DATABASE_PUBLIC_URL", "")  
    APP_BASE_URL: str = os.getenv("APP_BASE_URL", "http://localhost:8080")
    SECRET_KEY: str = os.getenv("SECRET_KEY", "7n9fjq_secure_key_2026")

    # --- Auth & JWT Settings (Requirement #130) ---
    JWT_SECRET: str = os.getenv("JWT_SECRET", "supersecret256bitkeyhere")
    JWT_ALG: str = "HS256"
    ACCESS_TOKEN_MIN: int = 120
    RESET_TOKEN_MINUTES: int = 30
    VERIFY_TOKEN_HOURS: int = 24
    PASSLIB_MAX_PASSWORD_SIZE: int = 1024
    
    # --- Cookie & Domain Settings ---
    COOKIE_DOMAIN: str = os.getenv("COOKIE_DOMAIN", "")
    COOKIE_SECURE: bool = os.getenv("COOKIE_SECURE", "False").lower() == "true"
    
    # --- Google OAuth & API Keys (Requirement #15) ---
    OAUTH_GOOGLE_CLIENT_ID: str = os.getenv("GOOGLE_CLIENT_ID", "")
    OAUTH_GOOGLE_CLIENT_SECRET: str = os.getenv("GOOGLE_CLIENT_SECRET", "")
    OAUTH_GOOGLE_REDIRECT_URI: str = os.getenv("GOOGLE_REDIRECT_URI", "")
    GOOGLE_BUSINESS_API_KEY: str = os.getenv("GOOGLE_BUSINESS_API_KEY", "")
    GOOGLE_MAPS_API_KEY: str = os.getenv("GOOGLE_MAPS_API_KEY", "")
    GOOGLE_PLACES_API_KEY: str = os.getenv("GOOGLE_PLACES_API_KEY", "")

    # --- SMTP / Email Settings ---
    SMTP_HOST: str = os.getenv("SMTP_HOST", "localhost")
    SMTP_USERNAME: str = os.getenv("SMTP_USERNAME", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    SMTP_FROM_EMAIL: str = os.getenv("SMTP_FROM_EMAIL", "noreply@reviewsaas.com")
    SMTP_FROM_NAME: str = os.getenv("SMTP_FROM_NAME", "Review SaaS")
    
    # --- Auth Security Logic ---
    LOCKOUT_THRESHOLD: int = 5
    LOCKOUT_MINUTES: int = 15

    # --- Configuration Logic ---
    # Requirement: Allow extra environment variables without crashing
    model_config = SettingsConfigDict(
        env_file=".env", 
        extra="ignore"  # This prevents the "Extra inputs" error on Railway
    )

settings = Settings()
