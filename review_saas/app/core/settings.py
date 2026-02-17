"""
Centralized settings loader for the app.

Loads environment variables (works locally with .env and on Railway/other hosts).
Only safe values are exposed to templates (e.g., GOOGLE_MAPS_API_KEY via context processor).
"""

import os
from dataclasses import dataclass
from dotenv import load_dotenv

# Load .env once at import (safe in dev; on hosted envs vars already exist)
load_dotenv()


@dataclass(frozen=True)
class Settings:
    SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-secret")
    GOOGLE_MAPS_API_KEY: str = os.getenv("GOOGLE_MAPS_API_KEY", "")
    DEBUG: bool = os.getenv("DEBUG", "1") == "1"
    PORT: int = int(os.getenv("PORT", "5000"))
    # Extend here when you add DB, Redis, etc.
    # DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///app.db")
    # BCRYPT_LOG_ROUNDS: int = int(os.getenv("BCRYPT_LOG_ROUNDS", "12"))


def settings_dict() -> dict:
    """
    Returns a plain dict suitable for app.config.update(...)
    """
    s = Settings()
    return {
        "SECRET_KEY": s.SECRET_KEY,
        "GOOGLE_MAPS_API_KEY": s.GOOGLE_MAPS_API_KEY,
        "DEBUG": s.DEBUG,
        "PORT": s.PORT,
        # "DATABASE_URL": s.DATABASE_URL,
        # "SECURITY_BCRYPT_LOG_ROUNDS": s.BCRYPT_LOG_ROUNDS,
    }
