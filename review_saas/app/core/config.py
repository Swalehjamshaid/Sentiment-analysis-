# filename: app/core/config.py
from pydantic import BaseSettings

class Settings(BaseSettings):
    ENVIRONMENT: str = "development"
    APP_NAME: str = "ReviewSaaS"
    DEBUG: bool = True
    SECRET_KEY: str = "change-me"
    DATABASE_URL: str

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()
