# File: app/core/config.py

import os
from pydantic_settings import BaseSettings, SettingsConfigDict, validator

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")  # optional, auto-load .env

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

# instantiate settings
settings = Settings()
