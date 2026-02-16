# app/core/settings.py
from pydantic import BaseSettings


class Settings(BaseSettings):
    # Expose your Google Maps key via env; do not hardcode secrets.
    GOOGLE_MAPS_API_KEY: str = ""

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
``
