# FILE: app/db.py

from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from .core.config import Settings
import logging
import os

# Initialize Flask-SQLAlchemy and Migrate
db = SQLAlchemy()
migrate = Migrate()
log = logging.getLogger("app.db")

def init_db(app):
    """
    Initializes the database with settings for both Development (SQLite) 
    and Production (PostgreSQL) as per Requirement 124.
    """
    settings = Settings()
    
    # Core Database URI (Requirement 124)
    database_url = settings.database_url
    
    # Fix for newer SQLAlchemy/Heroku/Railway 'postgres://' vs 'postgresql://'
    if database_url and database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # Connection Pool settings for Scalability (Requirement 131)
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        "pool_pre_ping": True,  # Check connection health before use
        "pool_recycle": 3600,   # Recycle connections every hour
        "pool_size": 10,        # Max permanent connections
        "max_overflow": 20      # Extra temporary connections during spikes
    }

    # Security: SSL enforcement for Production (Requirement 18 & 129)
    if os.getenv("FLASK_ENV") == "production":
        app.config['SQLALCHEMY_ENGINE_OPTIONS']["connect_args"] = {
            "sslmode": "require"
        }

    db.init_app(app)
    migrate.init_app(app, db)

    # Automated Setup for MVP/Development (Requirement 124)
    if os.getenv("DB_AUTO_CREATE", "0") == "1":
        with app.app_context():
            try:
                log.info("Checking database schema...")
                db.create_all()  # Creates tables based on updated models.py
                log.info("Database tables verified/created successfully.")
            except Exception as e:
                log.error(f"Database initialization failed: {e}")

    # Log successful initialization
    log.info(f"Database configured for: {database_url.split('@')[-1] if '@' in database_url else 'Local/Internal'}")
