"""
Application entry point.
Creates the Flask app, injects template globals, and supports both:
 - Local dev: python app/main.py   (or python -m app.main from root)
 - Production: gunicorn "app.main:app"
"""

from __future__ import annotations

import sys
from pathlib import Path
from flask import Flask, redirect, url_for

# Ensure relative imports work even if cwd is project root
sys.path.insert(0, str(Path(__file__).parent.resolve()))

# Now safe to do relative imports
from .core.settings import settings_dict
from .routes.auth import auth_bp
from .routes.companies import companies_bp
from .routes.dashboard import dashboard_bp
from .routes.reviews import reviews_bp
from .routes.recipes import recipes_bp
from .routes.reports import reports_bp


def create_app() -> Flask:
    """App factory pattern."""
    app = Flask(__name__)

    # Load configuration from environment/settings
    app.config.update(settings_dict())

    # ---------------- Register Blueprints ----------------
    blueprints = [
        auth_bp,
        companies_bp,
        dashboard_bp,
        reviews_bp,
        recipes_bp,
        reports_bp,
    ]

    for bp in blueprints:
        try:
            app.register_blueprint(bp)
        except Exception as e:
            print(f"Error registering blueprint {bp.name}: {e}", file=sys.stderr)
            raise

    # --------------- Template globals / context processors ---------------
    @app.context_processor
    def inject_globals():
        """Inject safe values into all templates."""
        return {
            "GOOGLE_MAPS_API_KEY": app.config.get("GOOGLE_MAPS_API_KEY", ""),
        }

    # --------------- Root redirect ---------------
    @app.route("/")
    def root():
        return redirect(url_for("dashboard.view_dashboard"))

    return app


# Expose module-level app for WSGI servers (Gunicorn, uWSGI, mod_wsgi, etc.)
app = create_app()


if __name__ == "__main__":
    # Local development server — never use in production
    # Flask's built-in server is single-threaded and insecure
    port = int(app.config.get("PORT", 5000))
    debug = bool(app.config.get("DEBUG", True))

    print(f"Starting Flask dev server on http://0.0.0.0:{port} (debug={debug})")
    app.run(
        host="0.0.0.0",
        port=port,
        debug=debug,
        use_reloader=debug,
        threaded=True,
    )
