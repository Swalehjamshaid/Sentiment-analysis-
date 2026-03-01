# File: app/core/config.py

import os
from pydantic import BaseSettings, validator

class Settings(BaseSettings):
    APP_NAME: str = "Review SaaS"
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "dev")
    DEBUG: bool = os.getenv("DEBUG", "False").lower() in ("true", "1", "yes")
    SECRET_KEY: str = os.getenv("SECRET_KEY", "super-secret-key")
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")

    @validator("DATABASE_URL")
    def check_db_url(cls, v):
        if not v:
            raise ValueError(
                "DATABASE_URL is empty! Set DATABASE_URL environment variable."
            )
        return v

settings = Settings()
