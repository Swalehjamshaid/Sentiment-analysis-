# filename: app/core/settings.py
from pydantic_settings import BaseSettings, SettingsConfigDict
# ... other imports

class Settings(BaseSettings):
    # ... all your existing fields ...
    DATABASE_URL: str = 'sqlite:///./app.db'

    model_config = SettingsConfigDict(
        env_file='.env',
        extra='allow',
        env_ignore_empty=True  # <--- ADD THIS LINE
    )

settings = Settings()
