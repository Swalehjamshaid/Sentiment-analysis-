# filename: app/db.py
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from .core.config import Settings

# Flask-SQLAlchemy handles sessions/engines for us

db = SQLAlchemy()
migrate = Migrate()

def init_db(app):
    settings = Settings()
    app.config['SQLALCHEMY_DATABASE_URI'] = settings.database_url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    migrate.init_app(app, db)
