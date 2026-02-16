
import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()

SECRET_KEY = os.getenv('SECRET_KEY', 'dev_secret')
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv('ACCESS_TOKEN_EXPIRE_MINUTES', '60'))
ALLOWED_ORIGINS = [o.strip() for o in os.getenv('ALLOWED_ORIGINS', 'http://localhost:8000').split(',')]
COOKIE_SECURE = os.getenv('COOKIE_SECURE', 'False').lower() == 'true'
HTTPS_ONLY = os.getenv('HTTPS_ONLY', 'False').lower() == 'true'

DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///./app.db')

SMTP = {
    'host': os.getenv('SMTP_HOST', ''),
    'port': int(os.getenv('SMTP_PORT', '587')),
    'user': os.getenv('SMTP_USER', ''),
    'password': os.getenv('SMTP_PASSWORD', ''),
    'from': os.getenv('SMTP_FROM', 'noreply@example.com')
}

GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY', '')

GOOGLE_OAUTH = {
    'client_id': os.getenv('GOOGLE_CLIENT_ID', ''),
    'client_secret': os.getenv('GOOGLE_CLIENT_SECRET', ''),
    'redirect_uri': os.getenv('OAUTH_REDIRECT_URI', 'http://localhost:8000/oauth/google/callback')
}

TWOFA_ENABLED = os.getenv('TWOFA_ENABLED', 'False').lower() == 'true'

LOCKOUT_MAX_ATTEMPTS = 5
LOCKOUT_WINDOW_MIN = 15
LOCKOUT_DURATION_MIN = 15

TOKEN_EXPIRE_EMAIL_VERIFICATION_H = 24
TOKEN_EXPIRE_PASSWORD_RESET_MIN = 30

REVIEW_FETCH_MAX = 500
