# app/core/settings.py
from pydantic import BaseSettings


class Settings(BaseSettings):
    GOOGLE_MAPS_API_KEY: str = ""

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
``
