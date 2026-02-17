"""
Application entry point.
Creates the Flask app, injects template globals, and supports both:
 - Local dev:  python app/main.py
 - Production: gunicorn "app.main:app"
"""

from __future__ import annotations
from datetime import datetime
from flask import Flask, redirect, url_for
from app.core.settings import settings_dict

# ---------------- Blueprints ----------------
# Ensure absolute imports work
try:
    from app.routes.auth import auth_bp
    from app.routes.companies import companies_bp
    from app.routes.dashboard import dashboard_bp
    from app.routes.reviews import reviews_bp
    from app.routes.recipes import recipes_bp
    from app.routes.reports import reports_bp
except ModuleNotFoundError as e:
    import sys, os
    # Add project root to sys.path in case relative imports fail in Gunicorn
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from app.routes.auth import auth_bp
    from app.routes.companies import companies_bp
    from app.routes.dashboard import dashboard_bp
    from app.routes.reviews import reviews_bp
    from app.routes.recipes import recipes_bp
    from app.routes.reports import reports_bp


def create_app() -> Flask:
    """App factory."""
    app = Flask(__name__)

    # Load config from environment via settings
    app.config.update(settings_dict())

    # Register blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(companies_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(reviews_bp)
    app.register_blueprint(recipes_bp)
    app.register_blueprint(reports_bp)

    # Inject template globals
    @app.context_processor
    def inject_globals():
        return {
            "GOOGLE_MAPS_API_KEY": app.config.get("GOOGLE_MAPS_API_KEY", ""),
            "now": lambda: datetime.utcnow().year,
        }

    # Healthcheck for Railway
    @app.route("/healthz")
    def healthz():
        return {"status": "ok"}, 200

    # Root redirect to dashboard
    @app.route("/")
    def root():
        return redirect(url_for("dashboard.view_dashboard"))

    return app


# Expose WSGI module-level app
app = create_app()

if __name__ == "__main__":
    # Local dev server
    app.run(
        host="0.0.0.0",
        port=int(app.config.get("PORT", 5000)),
        debug=bool(app.config.get("DEBUG", True)),
    )
