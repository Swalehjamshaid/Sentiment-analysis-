"""
Centralized settings loader for the app.

Loads environment variables (.env locally, environment on host).
"""

import os
from dataclasses import dataclass
from dotenv import load_dotenv

# Load .env in development; on hosted platforms env vars already exist
load_dotenv()


@dataclass(frozen=True)
class Settings:
    SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-secret")
    GOOGLE_MAPS_API_KEY: str = os.getenv("GOOGLE_MAPS_API_KEY", "")
    DEBUG: bool = os.getenv("DEBUG", "1") == "1"
    PORT: int = int(os.getenv("PORT", "5000"))


def settings_dict() -> dict:
    s = Settings()
    return {
        "SECRET_KEY": s.SECRET_KEY,
        "GOOGLE_MAPS_API_KEY": s.GOOGLE_MAPS_API_KEY,
        "DEBUG": s.DEBUG,
        "PORT": s.PORT,
    }
