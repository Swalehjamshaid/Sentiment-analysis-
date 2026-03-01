# filename: app/core/config.py

from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # --------------------------
    # Environment & app info
    # --------------------------
    ENVIRONMENT: str = "development"
    APP_NAME: str = "ReviewSaaS"
    SECRET_KEY: str
    DEBUG: bool = False

    # --------------------------
    # Security & tokens
    # --------------------------
    ACCESS_TOKEN_MIN: int = 120
    JWT_ALG: str = "HS256"
    JWT_SECRET: str
    LOCKOUT_MINUTES: int = 15
    LOCKOUT_THRESHOLD: int = 5
    RESET_TOKEN_MINUTES: int = 30
    VERIFY_TOKEN_HOURS: int = 24
    PASSLIB_MAX_PASSWORD_SIZE: int = 1024

    # --------------------------
    # Cookies
    # --------------------------
    COOKIE_DOMAIN: str
    COOKIE_SECURE: bool = True

    # --------------------------
    # Database
    # --------------------------
    DATABASE_URL: str
    DATABASE_PUBLIC_URL: str

    # --------------------------
    # Google APIs
    # --------------------------
    GOOGLE_BUSINESS_API_KEY: str
    GOOGLE_MAPS_API_KEY: str
    GOOGLE_PLACES_API_KEY: str

    # --------------------------
    # OAuth
    # --------------------------
    OAUTH_GOOGLE_CLIENT_ID: str
    OAUTH_GOOGLE_CLIENT_SECRET: str
    OAUTH_GOOGLE_REDIRECT_URI: str

    # --------------------------
    # SMTP / email
    # --------------------------
    SMTP_FROM_EMAIL: str
    SMTP_FROM_NAME: str
    SMTP_HOST: str
    SMTP_PORT: int
    SMTP_USERNAME: str
    SMTP_PASSWORD: str

    # --------------------------
    # Pydantic Settings config
    # --------------------------
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True
    )

# Create a singleton settings object
settings = Settings()
