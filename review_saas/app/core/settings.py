from pydantic_settings import BaseSettings

    class Settings(BaseSettings):
        APP_NAME: str = "Reputation Management SaaS"
        SECRET_KEY: str = "change-me"
        DATABASE_URL: str = "sqlite+aiosqlite:///./app/data/app.db"
        GOOGLE_API_KEY: str | None = None
        SMTP_HOST: str | None = None
        SMTP_PORT: int = 587
        SMTP_USER: str | None = None
        SMTP_PASS: str | None = None
        FROM_EMAIL: str = "no-reply@example.com"
        JWT_EXP_MINUTES: int = 60

        class Config:
            env_file = ".env"

    settings = Settings()