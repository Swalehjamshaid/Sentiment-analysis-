# FILE: app/db.py

from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from .core.config import Settings
import logging, os

db = SQLAlchemy()
migrate = Migrate()
log = logging.getLogger("app.db")

def init_db(app):
    settings = Settings()
    app.config['SQLALCHEMY_DATABASE_URI'] = settings.database_url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    db.init_app(app)
    migrate.init_app(app, db)

    # Optional: auto-create tables on startup for non-migration environments
    if os.getenv("DB_AUTO_CREATE", "0") == "1":
        with app.app_context():
            log.info("Ensuring tables exist...")
            db.create_all()  # will create only missing tables
            log.info("Database sync complete.")
