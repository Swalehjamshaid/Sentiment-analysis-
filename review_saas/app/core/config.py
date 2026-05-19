# filename: review_saas/app/core/config.py

import os

from pathlib import Path

from typing import Optional

from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict
)

from pydantic import (
    model_validator
)

# ==========================================================
# SETTINGS
# ==========================================================

class Settings(BaseSettings):

    """
    TRUSTLYTICS AI SAAS
    ENTERPRISE CONFIGURATION
    FULLY RAILWAY COMPATIBLE
    """

    # ======================================================
    # APP
    # ======================================================

    APP_NAME: str = "Review-Intel-AI"

    APP_BASE_URL: str = os.getenv(
        "APP_BASE_URL",
        "https://sentiment-analysis-production-f96a.up.railway.app"
    )

    BASE_URL: str = os.getenv(
        "BASE_URL",
        "https://trustlytics.online"
    )

    FRONTEND_URL: str = os.getenv(
        "FRONTEND_URL",
        "https://trustlytics.online"
    )

    ENVIRONMENT: str = os.getenv(
        "ENVIRONMENT",
        "production"
    )

    DEBUG: bool = os.getenv(
        "DEBUG",
        "False"
    ).lower() in (
        "true",
        "1",
        "t"
    )

    # ======================================================
    # DATABASE
    # ======================================================

    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "sqlite+aiosqlite:///./test.db"
    )

    # ======================================================
    # SECURITY
    # ======================================================

    SECRET_KEY: str = os.getenv(
        "SECRET_KEY",
        "super-secret-key-jamshaid-2026"
    )

    JWT_SECRET: str = os.getenv(
        "JWT_SECRET",
        "jwt-secret"
    )

    SESSION_COOKIE_NAME: str = "session"

    # ======================================================
    # EMAIL
    # ======================================================

    MAIL_USERNAME: str = os.getenv(
        "MAIL_USERNAME",
        "roy.jamshaid@gmail.com"
    )

    MAIL_PASSWORD: str = os.getenv(
        "MAIL_PASSWORD",
        ""
    )

    MAIL_FROM: str = os.getenv(
        "MAIL_FROM",
        "noreply@reviewintel.ai"
    )

    MAIL_PORT: int = int(
        os.getenv(
            "MAIL_PORT",
            "587"
        )
    )

    MAIL_SERVER: str = os.getenv(
        "MAIL_SERVER",
        "smtp.gmail.com"
    )

    RESEND_API_KEY: str = os.getenv(
        "RESEND_API_KEY",
        ""
    )

    # ======================================================
    # GOOGLE
    # ======================================================

    GOOGLE_API_KEY: str = os.getenv(
        "GOOGLE_API_KEY",
        ""
    )

    GOOGLE_MAPS_API_KEY: Optional[str] = os.getenv(
        "GOOGLE_MAPS_API_KEY"
    )

    GOOGLE_PLACES_API_KEY: Optional[str] = os.getenv(
        "GOOGLE_PLACES_API_KEY"
    )

    GOOGLE_CLIENT_ID: str = os.getenv(
        "GOOGLE_CLIENT_ID",
        ""
    )

    GOOGLE_CLIENT_SECRET: str = os.getenv(
        "GOOGLE_CLIENT_SECRET",
        ""
    )

    GOOGLE_REDIRECT_URI: str = os.getenv(
        "GOOGLE_REDIRECT_URI",
        ""
    )

    # ======================================================
    # APIFY
    # ======================================================

    APIFY_TOKEN: str = os.getenv(
        "APIFY_TOKEN",
        ""
    )

    APIFY_API_TOKEN: str = os.getenv(
        "APIFY_API_TOKEN",
        ""
    )

    # ======================================================
    # AI PROVIDERS
    # ======================================================

    OPENAI_API_KEY: str = os.getenv(
        "OPENAI_API_KEY",
        ""
    )

    GEMINI_API_KEY: str = os.getenv(
        "GEMINI_API_KEY",
        ""
    )

    GROQ_API_KEY: str = os.getenv(
        "GROQ_API_KEY",
        ""
    )

    DEEPSEEK_API_KEY: str = os.getenv(
        "DEEPSEEK_API_KEY",
        ""
    )

    # ======================================================
    # SCRAPING PROVIDERS
    # ======================================================

    SERPAPI_KEY: str = os.getenv(
        "SERPAPI_KEY",
        ""
    )

    SERPER_API_KEY: str = os.getenv(
        "SERPER_API_KEY",
        ""
    )

    OUTSCRAPER_API_KEY: Optional[str] = os.getenv(
        "OUTSCRAPER_API_KEY"
    )

    SCRAPEOPS_API_KEY: str = os.getenv(
        "SCRAPEOPS_API_KEY",
        ""
    )

    SCRAPELESS_API_KEY: str = os.getenv(
        "SCRAPELESS_API_KEY",
        ""
    )

    SCRAPE_DO_TOKEN: str = os.getenv(
        "SCRAPE_DO_TOKEN",
        ""
    )

    PROXYSCRAPE_API_KEY: str = os.getenv(
        "PROXYSCRAPE_API_KEY",
        ""
    )

    # ======================================================
    # PROXY
    # ======================================================

    PROXY_SERVER: str = os.getenv(
        "PROXY_SERVER",
        ""
    )

    PROXY_USERNAME: str = os.getenv(
        "PROXY_USERNAME",
        ""
    )

    PROXY_PASSWORD: str = os.getenv(
        "PROXY_PASSWORD",
        ""
    )

    # ======================================================
    # PLAYWRIGHT
    # ======================================================

    PLAYWRIGHT_BROWSERS_PATH: str = os.getenv(
        "PLAYWRIGHT_BROWSERS_PATH",
        "/ms-playwright"
    )

    NIXPACKS_PLAYWRIGHT_VERSION: str = os.getenv(
        "NIXPACKS_PLAYWRIGHT_VERSION",
        "1.52.0"
    )

    # ======================================================
    # PYTHON
    # ======================================================

    PYTHONPATH: str = os.getenv(
        "PYTHONPATH",
        "/app"
    )

    PORT: str = os.getenv(
        "PORT",
        "8080"
    )

    # ======================================================
    # REDIS
    # ======================================================

    REDIS_URL: str = os.getenv(
        "REDIS_URL",
        ""
    )

    # ======================================================
    # TEMPLATE PATHS
    # ======================================================

    TEMPLATES_DIR: str = ""

    STATIC_DIR: str = ""

    # ======================================================
    # PYDANTIC
    # ======================================================

    model_config = SettingsConfigDict(

        env_file=".env",

        extra="ignore",

        case_sensitive=False
    )

    # ======================================================
    # FINALIZE CONFIG
    # ======================================================

    @model_validator(mode="after")

    def _finalize_config(self) -> "Settings":

        # ==================================================
        # PATH ALIGNMENT
        # ==================================================

        current_path = Path(
            __file__
        ).resolve()

        base_app_dir = current_path.parent.parent

        self.TEMPLATES_DIR = str(
            base_app_dir / "templates"
        )

        self.STATIC_DIR = str(
            base_app_dir / "static"
        )

        # ==================================================
        # GOOGLE KEY NORMALIZATION
        # ==================================================

        google_key = (

            self.GOOGLE_MAPS_API_KEY

            or

            self.GOOGLE_API_KEY
        )

        if google_key:

            self.GOOGLE_API_KEY = google_key

            self.GOOGLE_MAPS_API_KEY = google_key

        # ==================================================
        # APIFY KEY NORMALIZATION
        # ==================================================

        if not self.APIFY_TOKEN:

            self.APIFY_TOKEN = self.APIFY_API_TOKEN

        return self

# ==========================================================
# INITIALIZE SETTINGS
# ==========================================================

settings = Settings()
