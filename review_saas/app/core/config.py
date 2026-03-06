# File: review_saas/app/core/config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # ... other settings ...

    # Match this exactly to your .env file
    OUTSCAPTER_KEY: str  

    class Config:
        case_sensitive = True
        env_file = ".env"
        extra = "ignore"

settings = Settings()
