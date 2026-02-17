"""
Centralized settings loader for the app.
Loads environment variables (.env locally, environment on Railway/Render/etc.).
Safe for production: no hard-coded secrets, optional .env fallback.
"""

import os
from dataclasses import dataclass
from typing import Optional
from dotenv import load_dotenv

# Load .env file only if it exists (safe for Railway - env vars are already set there)
load_dotenv()  # does nothing if .env is missing

@dataclass(frozen=True)
class Settings:
    # Core security
    SECRET_KEY: str = os.getenv("SECRET_KEY") or "dev-secret-key-change-me-immediately"
    
    # Google APIs (injected into templates)
    GOOGLE_MAPS_API_KEY: str = os.getenv("GOOGLE_MAPS_API_KEY", "")
    GOOGLE_PLACES_API_KEY: Optional[str] = os.getenv("GOOGLE_PLACES_API_KEY")  # optional if separate key
    
    # Debug & server
    DEBUG: bool = os.getenv("DEBUG", "False").lower() in ("true", "1", "t")
    PORT: int = int(os.getenv("PORT", "5000"))
    
    # Authentication tokens
    SECURITY_PASSWORD_SALT: str = os.getenv("SECURITY_PASSWORD_SALT") or "salt-for-hashing-tokens"
    ACCESS_TOKEN_MIN: int = int(os.getenv("ACCESS_TOKEN_MIN", "30"))          # minutes
    RESET_TOKEN_MINUTES: int = int(os.getenv("RESET_TOKEN_MINUTES", "30"))
    VERIFY_TOKEN_HOURS: int = int(os.getenv("VERIFY_TOKEN_HOURS", "24"))
    
    # Email/SMTP for verification, reset, alerts
    MAIL_SERVER: str = os.getenv("MAIL_SERVER", "smtp.gmail.com")
    MAIL_PORT: int = int(os.getenv("MAIL_PORT", "587"))
    MAIL_USE_TLS: bool = os.getenv("MAIL_USE_TLS", "True").lower() in ("true", "1", "t")
    MAIL_USERNAME: Optional[str] = os.getenv("MAIL_USERNAME")
    MAIL_PASSWORD: Optional[str] = os.getenv("MAIL_PASSWORD")
    MAIL_DEFAULT_SENDER: str = os.getenv("MAIL_DEFAULT_SENDER", "no-reply@yourdomain.com")
    
    # OAuth (Google login)
    OAUTH_GOOGLE_CLIENT_ID: Optional[str] = os.getenv("OAUTH_GOOGLE_CLIENT_ID")
    OAUTH_GOOGLE_CLIENT_SECRET: Optional[str] = os.getenv("OAUTH_GOOGLE_CLIENT_SECRET")
    
    # JWT (for token-based auth if used)
    JWT_SECRET: str = os.getenv("JWT_SECRET") or SECRET_KEY  # fallback to SECRET_KEY

    # Optional 2FA / other
    TWO_FACTOR_ISSUER: str = os.getenv("TWO_FACTOR_ISSUER", "Reputation SaaS")


def settings_dict() -> dict:
    """
    Returns all settings as a flat dict for Flask app.config.update().
    Only exposes safe/public values to templates via context_processor.
    """
    s = Settings()
    return {
        # Safe to expose to templates
        "GOOGLE_MAPS_API_KEY": s.GOOGLE_MAPS_API_KEY,
        
        # Internal / secret - not exposed to templates
        "SECRET_KEY": s.SECRET_KEY,
        "DEBUG": s.DEBUG,
        "PORT": s.PORT,
        "SECURITY_PASSWORD_SALT": s.SECURITY_PASSWORD_SALT,
        "ACCESS_TOKEN_MIN": s.ACCESS_TOKEN_MIN,
        "RESET_TOKEN_MINUTES": s.RESET_TOKEN_MINUTES,
        "VERIFY_TOKEN_HOURS": s.VERIFY_TOKEN_HOURS,
        "MAIL_SERVER": s.MAIL_SERVER,
        "MAIL_PORT": s.MAIL_PORT,
        "MAIL_USE_TLS": s.MAIL_USE_TLS,
        "MAIL_USERNAME": s.MAIL_USERNAME,
        "MAIL_PASSWORD": s.MAIL_PASSWORD,
        "MAIL_DEFAULT_SENDER": s.MAIL_DEFAULT_SENDER,
        "OAUTH_GOOGLE_CLIENT_ID": s.OAUTH_GOOGLE_CLIENT_ID,
        "OAUTH_GOOGLE_CLIENT_SECRET": s.OAUTH_GOOGLE_CLIENT_SECRET,
        "JWT_SECRET": s.JWT_SECRET,
        "TWO_FACTOR_ISSUER": s.TWO_FACTOR_ISSUER,
    }
