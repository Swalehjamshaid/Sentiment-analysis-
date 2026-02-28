# filename: app/core/config.py
import os
from dataclasses import dataclass

@dataclass
class Settings:
    # Keep both names for backward compatibility across your code
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./app.db")
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./app.db")
    secret_key: str = os.getenv("SECRET_KEY", "dev-secret")
    SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-secret")
    google_maps_api_key: str = os.getenv("GOOGLE_MAPS_API_KEY", "")
    GOOGLE_MAPS_API_KEY: str = os.getenv("GOOGLE_MAPS_API_KEY", "")

# Instance-style (used by some modules)
settings = Settings()
