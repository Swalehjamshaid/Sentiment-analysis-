# filename: app/app/core/config.py
import os
from functools import lru_cache

class Settings:
    app_name: str = 'ReviewSaaS'
    secret_key: str = os.getenv('SESSION_SECRET', 'change-me')
    database_url: str = os.getenv('DATABASE_URL', 'sqlite:///./app.db')
    google_maps_api_key: str = os.getenv('GOOGLE_MAPS_API_KEY', '')
    google_places_api_key: str = os.getenv('GOOGLE_PLACES_API_KEY', '')
    google_business_api_key: str = os.getenv('GOOGLE_BUSINESS_API_KEY', '')
    app_base_url: str = os.getenv('APP_BASE_URL', '')
    cookie_domain: str = os.getenv('COOKIE_DOMAIN', '')
    cookie_secure: bool = os.getenv('COOKIE_SECURE', 'true').lower() == 'true'
    jwt_secret: str = os.getenv('JWT_SECRET', 'change-this')
    jwt_alg: str = os.getenv('JWT_ALG', 'HS256')

@lru_cache
def get_settings() -> Settings:
    return Settings()
