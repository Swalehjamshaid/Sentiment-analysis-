"""
Application entry point.
Creates the Flask app, injects template globals, and supports both:
 - Local dev: python app/main.py
 - Production: gunicorn "app.main:app"
"""

from __future__ import annotations

import os
import time
import sys
from pathlib import Path
from flask import Flask, redirect, url_for
from flask_login import LoginManager

# Safety: ensure app/ directory is in sys.path (fixes Railway cwd = /app/)
package_dir = Path(__file__).parent.resolve()
if str(package_dir) not in sys.path:
    sys.path.insert(0, str(package_dir))

# Relative imports for blueprints
from .core.settings import settings_dict
from .routes.auth import auth_bp
from .routes.companies import companies_bp
from .routes.dashboard import dashboard_bp
from .routes.reviews import reviews_bp
from .routes.recipes import recipes_bp
from .routes.reports import reports_bp
from .routes.health import health_bp   # health check - must be independent

# Flask-Login setup (global, but init_app later)
login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message_category = "info"

# Delayed DB initialization (moved out of module level)
db = None  # will be initialized in create_app after wait

def wait_for_db():
    """Wait for PostgreSQL to be ready before initializing DB connection."""
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("WARNING: DATABASE_URL not set - skipping DB wait")
        return

    print("Waiting for database to be ready...")
    import psycopg2
    for attempt in range(15):  # ~45 seconds total
        try:
            conn = psycopg2.connect(db_url)
            conn.close()
            print("Database is ready!")
            return
        except psycopg2.OperationalError as e:
            print(f"DB not ready yet (attempt {attempt+1}/15): {e}")
            time.sleep(3)
        except Exception as e:
            print(f"Unexpected DB error: {e}")
            break

    raise Exception("Database not ready after 45 seconds - check Postgres service")


def create_app() -> Flask:
    """App factory - safe for Railway startup."""
    global db  # reference to module-level db

    app = Flask(__name__)

    # Load config
    app.config.update(settings_dict())

    # SQLAlchemy config
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # Wait for DB before initializing SQLAlchemy (critical!)
    wait_for_db()

    # Now safe to initialize DB
    from . import db as db_module  # delayed import to avoid circular issues
    db = db_module.db
    db.init_app(app)

    # Initialize Flask-Login
    login_manager.init_app(app)

    # ---------------- Blueprints ----------------
    app.register_blueprint(auth_bp)
    app.register_blueprint(companies_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(reviews_bp)
    app.register_blueprint(recipes_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(health_bp)  # healthcheck - must be last and independent

    # --------------- Template globals ---------------
    @app.context_processor
    def inject_globals():
        return {
            "GOOGLE_MAPS_API_KEY": app.config.get("GOOGLE_MAPS_API_KEY", ""),
        }

    # --------------- Root redirect ---------------
    @app.route("/")
    def root():
        return redirect(url_for("dashboard.view_dashboard"))

    return app


# Expose app for Gunicorn
app = create_app()


if __name__ == "__main__":
    # Local dev server
    app.run(
        host="0.0.0.0",
        port=int(app.config.get("PORT", 5000)),
        debug=bool(app.config.get("DEBUG", True)),
    )
