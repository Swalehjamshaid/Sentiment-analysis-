# filename: app/core/config.py
import os
from dataclasses import dataclass
from datetime import timedelta

@dataclass
class Settings:
    secret_key: str = os.getenv('SECRET_KEY', 'dev-secret')
    database_url: str = os.getenv('DATABASE_URL', 'sqlite:///app.db')

    # JWT & sessions
    jwt_secret: str = os.getenv('JWT_SECRET', 'jwt-secret')
    jwt_cookie_name: str = os.getenv('JWT_COOKIE_NAME', 'auth_token')
    jwt_exp_minutes: int = int(os.getenv('JWT_EXP_MINUTES', '60'))

    # Security policies
    lockout_threshold: int = int(os.getenv('LOCKOUT_THRESHOLD', '5'))
    lockout_minutes: int = int(os.getenv('LOCKOUT_MINUTES', '15'))

    # Token expiries
    verify_token_hours: int = int(os.getenv('VERIFY_TOKEN_HOURS', '24'))
    reset_token_minutes: int = int(os.getenv('RESET_TOKEN_MINUTES', '30'))

    # Google APIs
    google_maps_api_key: str = os.getenv('GOOGLE_MAPS_API_KEY', '')

    # Email settings (stub or SMTP)
    smtp_host: str = os.getenv('SMTP_HOST', '')
    smtp_port: int = int(os.getenv('SMTP_PORT', '587')) if os.getenv('SMTP_PORT') else 587
    smtp_user: str = os.getenv('SMTP_USER', '')
    smtp_pass: str = os.getenv('SMTP_PASS', '')
    from_email: str = os.getenv('FROM_EMAIL', 'noreply@example.com')
