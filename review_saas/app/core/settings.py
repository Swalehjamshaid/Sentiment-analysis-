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
    # Required / Security
    SECRET_KEY: str = os.getenv("SECRET_KEY") or "dev-secret-key-change-me"
    # Google Maps (injected into templates)
    GOOGLE_MAPS_API_KEY: str = os.getenv("GOOGLE_MAPS_API_KEY", "")
    # Debug & Port
    DEBUG: bool = os.getenv("DEBUG", "False").lower() == "true"
    PORT: int = int(os.getenv("PORT", "5000"))
    # Authentication & Security extras
    SECURITY_PASSWORD_SALT: str = os.getenv("SECURITY_PASSWORD_SALT", "salt-for-hashing-tokens")
    MAIL_SERVER: str = os.getenv("MAIL_SERVER", "smtp.gmail.com")
    MAIL_PORT: int = int(os.getenv("MAIL_PORT", "587"))
    MAIL_USE_TLS: bool = os.getenv("MAIL_USE_TLS", "True").lower() == "true"
    MAIL_USERNAME: str = os.getenv("MAIL_USERNAME")
    MAIL_PASSWORD: str = os.getenv("MAIL_PASSWORD")
    MAIL_DEFAULT_SENDER: str = os.getenv("MAIL_DEFAULT_SENDER", "no-reply@yourdomain.com")

def settings_dict() -> dict:
    s = Settings()
    return {
        "SECRET_KEY": s.SECRET_KEY,
        "GOOGLE_MAPS_API_KEY": s.GOOGLE_MAPS_API_KEY,
        "DEBUG": s.DEBUG,
        "PORT": s.PORT,
        "SECURITY_PASSWORD_SALT": s.SECURITY_PASSWORD_SALT,
        "MAIL_SERVER": s.MAIL_SERVER,
        "MAIL_PORT": s.MAIL_PORT,
        "MAIL_USE_TLS": s.MAIL_USE_TLS,
        "MAIL_USERNAME": s.MAIL_USERNAME,
        "MAIL_PASSWORD": s.MAIL_PASSWORD,
        "MAIL_DEFAULT_SENDER": s.MAIL_DEFAULT_SENDER,
    }
