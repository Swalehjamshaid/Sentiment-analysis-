# filename: app/core/settings.py
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    # ... existing fields (APP_NAME, DATABASE_URL, etc.)

    # ADD THESE LINES (Requirement #15 - OAuth Login)
    OAUTH_GOOGLE_CLIENT_ID: Optional[str] = None
    OAUTH_GOOGLE_CLIENT_SECRET: Optional[str] = None
    OAUTH_GOOGLE_REDIRECT_URI: Optional[str] = None

    model_config = SettingsConfigDict(
        env_file='.env',
        extra='allow',
        env_ignore_empty=True
    )

settings = Settings()
