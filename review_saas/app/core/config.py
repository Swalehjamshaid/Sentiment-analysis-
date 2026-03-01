# filename: app/core/config.py

from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # -----------------------
    # App settings
    # -----------------------
    APP_NAME: str = "ReviewSaaS"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    SECRET_KEY: str
    APP_BASE_URL: str

    # -----------------------
    # Database
    # -----------------------
    DATABASE_URL: str
    DATABASE_PUBLIC_URL: str

    # -----------------------
    # JWT
    # -----------------------
    JWT_SECRET: str
    JWT_ALG: str = "HS256"
    ACCESS_TOKEN_MIN: int = 120

    # -----------------------
    # Cookie settings
    # -----------------------
    COOKIE_DOMAIN: str = ""
    COOKIE_SECURE: bool = True

    # -----------------------
    # Google APIs
    # -----------------------
    GOOGLE_BUSINESS_API_KEY: str
    GOOGLE_MAPS_API_KEY: str
    GOOGLE_PLACES_API_KEY: str

    # -----------------------
    # OAuth Google
    # -----------------------
    OAUTH_GOOGLE_CLIENT_ID: str
    OAUTH_GOOGLE_CLIENT_SECRET: str
    OAUTH_GOOGLE_REDIRECT_URI: str

    # -----------------------
    # Password & Security
    # -----------------------
    PASSLIB_MAX_PASSWORD_SIZE: int = 1024
    LOCKOUT_MINUTES: int = 15
    LOCKOUT_THRESHOLD: int = 5
    RESET_TOKEN_MINUTES: int = 30
    VERIFY_TOKEN_HOURS: int = 24

    # -----------------------
    # SMTP (email)
    # -----------------------
    SMTP_FROM_EMAIL: str
    SMTP_FROM_NAME: str
    SMTP_HOST: str
    SMTP_PORT: int = 587
    SMTP_USERNAME: str
    SMTP_PASSWORD: str

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
