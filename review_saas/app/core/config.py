from pydantic_settings import BaseSettings

    class Settings(BaseSettings):
        APP_NAME: str = "Review SaaS Pro"
        SECRET_KEY: str = "change-me"
        DATABASE_URL: str = "sqlite:///./app.db"
        FORCE_HTTPS: int = 1
        TOKEN_MINUTES: int = 60
        ENABLE_2FA: int = 0

        GOOGLE_CLIENT_ID: str | None = None
        GOOGLE_CLIENT_SECRET: str | None = None
        OAUTH_REDIRECT_URL: str | None = None
        GOOGLE_API_KEY: str | None = None

        SMTP_HOST: str | None = None
        SMTP_PORT: int = 587
        SMTP_USER: str | None = None
        SMTP_PASS: str | None = None
        FROM_EMAIL: str = "no-reply@example.com"

        ENABLE_SCHEDULER: int = 0
        FETCH_CRON: str = "0 0 * * *"

        ENABLE_ALERTS: int = 0
        NEGATIVE_ALERT_THRESHOLD: int = 1

        REPORT_LOGO_URL: str | None = None

        class Config:
            env_file = ".env"

    settings = Settings()