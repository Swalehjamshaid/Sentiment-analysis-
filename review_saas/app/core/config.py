# filename: app/core/config.py
import os
from dataclasses import dataclass

@dataclass
class Settings:
    secret_key: str = os.getenv('SECRET_KEY', 'dev-secret')
    database_url: str = os.getenv('DATABASE_URL', 'sqlite:///app.db')
    google_maps_api_key: str = os.getenv('GOOGLE_MAPS_API_KEY', '')
