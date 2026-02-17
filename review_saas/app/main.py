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

# Ensure the parent directory of main.py is in sys.path (fixes Railway cwd = /app/)
package_dir = Path(__file__).parent.resolve()
if str(package_dir) not in sys.path:
    sys.path.insert(0, str(package_dir))

# Now use RELATIVE imports for blueprints
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

    # Load configuration
    app.config.update(settings_dict())

    # ---------------- Register Blueprints ----------------
    blueprints = [
        ("auth", auth_bp),
        ("companies", companies_bp),
        ("dashboard", dashboard_bp),
        ("reviews", reviews_bp),
        ("recipes", recipes_bp),
        ("reports", reports_bp),
    ]

    for name, bp in blueprints:
        try:
            app.register_blueprint(bp)
            print(f"Registered blueprint: {name}")
        except Exception as e:
            print(f"Failed to register blueprint '{name}': {e}", file=sys.stderr)
            raise

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
    port = int(app.config.get("PORT", 5000))
    debug = bool(app.config.get("DEBUG", True))
    print(f"Starting dev server on http://0.0.0.0:{port} (debug={debug})")
    app.run(
        host="0.0.0.0",
        port=port,
        debug=debug,
        use_reloader=debug,
        threaded=True,
    )
