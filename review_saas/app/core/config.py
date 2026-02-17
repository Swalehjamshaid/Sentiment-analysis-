from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # App
    APP_NAME: str = "Review SaaS Pro"

    # Secrets / DB
    SECRET_KEY: str = "change-me"
    DATABASE_URL: str = "sqlite:///./app.db"

    # Security / Auth
    FORCE_HTTPS: int = 1          # 1 = redirect to HTTPS when behind a proxy
    TOKEN_MINUTES: int = 60       # JWT lifetime
    ENABLE_2FA: int = 0           # 1 to require TOTP at login (when user has a secret)

    # OAuth (optional)
    GOOGLE_CLIENT_ID: str | None = None
    GOOGLE_CLIENT_SECRET: str | None = None
    OAUTH_REDIRECT_URL: str | None = None

    # Google Places (optional)
    GOOGLE_API_KEY: str | None = None

    # Email / SMTP
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USER: str | None = None
    SMTP_PASS: str | None = None
    FROM_EMAIL: str = "no-reply@example.com"

    # Scheduler (optional)
    ENABLE_SCHEDULER: int = 0
    FETCH_CRON: str = "0 0 * * *"  # daily at 00:00 UTC

    # Alerts (optional)
    ENABLE_ALERTS: int = 0
    NEGATIVE_ALERT_THRESHOLD: int = 1

    # PDF (optional)
    REPORT_LOGO_URL: str | None = None

    class Config:
        env_file = ".env"


settings = Settings()
