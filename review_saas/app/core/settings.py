import os
from dotenv import load_dotenv

load_dotenv()

def settings_dict():
    """Requirement 10: Technical Stack Configs"""
    return {
        # Section 10: Database Selection (PostgreSQL for Prod)
        "SQLALCHEMY_DATABASE_URI": os.getenv("DATABASE_URL", "sqlite:///reputation.db"),
        
        # Section 2 & 3: API Keys
        "GOOGLE_MAPS_API_KEY": os.getenv("GOOGLE_MAPS_API_KEY", ""),
        "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY", ""),
        
        # Section 1: Security & Session
        "SECRET_KEY": os.getenv("SECRET_KEY", "prod-security-key-123"),
        "SESSION_COOKIE_HTTPONLY": True,
        "PERMANENT_SESSION_LIFETIME": 3600 # 1 hour
    }
