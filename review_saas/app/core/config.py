import os
from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    # Requirement 122: Project Metadata
    PROJECT_NAME: str = "ReviewSaaS AI"
    PROJECT_VERSION: str = "1.0.0"

    # Requirement 124: Database Configuration
    # Railway provides DATABASE_URL automatically in production
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", 
        "postgresql://postgres:password@localhost:5432/review_db"
    )

    # Requirement 8 & 129: Security Settings
    SECRET_KEY: str = os.getenv("SECRET_KEY", "lahore-super-secret-key-2026-xyz")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours

    # Requirement 128: Google Places API Key
    GOOGLE_API_KEY: Optional[str] = os.getenv("GOOGLE_API_KEY", "")

    # Requirement 10: Account Lockout Configuration
    MAX_LOGIN_ATTEMPTS: int = 5
    LOCKOUT_DURATION_SECONDS: int = 300  # 5 minutes

    class Config:
        case_sensitive = True
        # Look for a .env file if it exists
        env_file = ".env"

# Create the instance that main.py is trying to import
settings = Settings()
