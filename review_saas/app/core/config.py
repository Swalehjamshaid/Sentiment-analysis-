import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    APP_NAME: str = "ReviewSaaS AI"
    
    # Requirement 124: Database Configuration
    # We use a default sqlite string so the app can at least START and show logs
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")

    model_config = SettingsConfigDict(
        extra='ignore',
        env_file=".env",
        case_sensitive=True
    )

    # This is likely what is causing your specific error message
    def __init__(self, **values):
        super().__init__(**values)
        if not self.DATABASE_URL:
            print("DATABASE_URL is empty. Please set it in your environment variables.")
            # Instead of crashing here, we could set a fallback:
            # self.DATABASE_URL = "sqlite:///./fallback.db"
