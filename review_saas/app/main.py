"""
Application entry point.
Creates the Flask app, injects template globals, and supports both:
 - Local dev: python app/main.py
 - Production: gunicorn "app.main:app"
"""

from __future__ import annotations

from flask import Flask, redirect, url_for

# Relative imports (safe for Railway cwd = project root)
from .core.settings import settings_dict
from .routes.auth import auth_bp
from .routes.companies import companies_bp
from .routes.dashboard import dashboard_bp
from .routes.reviews import reviews_bp
from .routes.recipes import recipes_bp
from .routes.reports import reports_bp
from .routes.health import health_bp   # ← NEW: import health blueprint


def create_app() -> Flask:
    """App factory."""
    app = Flask(__name__)

    # Load config from environment via settings
    app.config.update(settings_dict())

    # ---------------- Blueprints ----------------
    app.register_blueprint(auth_bp)
    app.register_blueprint(companies_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(reviews_bp)
    app.register_blueprint(recipes_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(health_bp)  # ← NEW: register health blueprint

    # --------------- Template globals ---------------
    @app.context_processor
    def inject_globals():
        # Expose only safe values
        return {
            "GOOGLE_MAPS_API_KEY": app.config.get("GOOGLE_MAPS_API_KEY", ""),
        }

    # --------------- Root redirect ---------------
    @app.route("/")
    def root():
        from flask import redirect, url_for
        return redirect(url_for("dashboard.view_dashboard"))

    return app


# Expose a module-level `app` for WSGI servers (gunicorn, mod_wsgi, etc.)
app = create_app()


if __name__ == "__main__":
    # Local dev server (avoid using in production)
    app.run(
        host="0.0.0.0",
        port=int(app.config.get("PORT", 5000)),
        debug=bool(app.config.get("DEBUG", True)),
    )
