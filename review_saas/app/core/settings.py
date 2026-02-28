# filename: app/core/settings.py
import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    APP_NAME: str = "ReviewSaaS"
    # Persistent SQLite database file
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./review_saas.db")
    
    SECRET_KEY: str = os.getenv("SECRET_KEY", "your-super-secret-key-change-me")
    APP_BASE_URL: str = os.getenv("APP_BASE_URL", "http://localhost:8080")
    
    # Auth Security
    LOCKOUT_THRESHOLD: int = 5
    LOCKOUT_MINUTES: int = 15
    COOKIE_SECURE: bool = False  # Set to True if using HTTPS/Production
    
    # Google OAuth Credentials
    # Register these at https://console.cloud.google.com/
    OAUTH_GOOGLE_CLIENT_ID: str = os.getenv("GOOGLE_CLIENT_ID", "YOUR_CLIENT_ID")
    OAUTH_GOOGLE_CLIENT_SECRET: str = os.getenv("GOOGLE_CLIENT_SECRET", "YOUR_CLIENT_SECRET")

    class Config:
        env_file = ".env"

settings = Settings()
