"""
Application entry point.
Creates the Flask app, injects template globals, and supports both:
 - Local dev: python app/main.py
 - Production: gunicorn "app.main:app"
"""

from __future__ import annotations

import sys
from pathlib import Path
from flask import Flask, redirect, url_for
from flask_login import LoginManager

# Ensure relative imports work from project root or inside app/
package_dir = Path(__file__).parent.resolve()
if str(package_dir) not in sys.path:
    sys.path.insert(0, str(package_dir))

from .core.settings import settings_dict
from .routes.auth import auth_bp
from .routes.companies import companies_bp
from .routes.dashboard import dashboard_bp
from .routes.reviews import reviews_bp
from .routes.recipes import recipes_bp
from .routes.reports import reports_bp

# Flask-Login setup
login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message_category = "info"

def create_app() -> Flask:
    """App factory."""
    app = Flask(__name__)

    # Load config
    app.config.update(settings_dict())

    # Initialize Flask-Login
    login_manager.init_app(app)

    # ---------------- Blueprints ----------------
    app.register_blueprint(auth_bp)
    app.register_blueprint(companies_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(reviews_bp)
    app.register_blueprint(recipes_bp)
    app.register_blueprint(reports_bp)

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

    # Optional: Update last_login on every request (point 27)
    @app.before_request
    def update_last_login():
        if current_user.is_authenticated:
            current_user.last_login_at = datetime.utcnow()
            db.session.commit()

    return app

# Expose app for Gunicorn
app = create_app()

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(app.config.get("PORT", 5000)),
        debug=bool(app.config.get("DEBUG", True)),
    )
