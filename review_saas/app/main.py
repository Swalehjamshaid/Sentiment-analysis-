"""
Application entry point.
Supports:
 - Local dev: python app/main.py
 - Production: gunicorn app.main:app
"""

from __future__ import annotations

import sys
from pathlib import Path
from flask import Flask, redirect, url_for

# Ensure package path
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
from .routes.health import health_bp


def create_app() -> Flask:
    app = Flask(__name__)

    # Load configuration safely
    app.config.update(settings_dict())

    # Register blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(companies_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(reviews_bp)
    app.register_blueprint(recipes_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(health_bp)

    @app.route("/")
    def root():
        return redirect(url_for("dashboard.view_dashboard"))

    return app


app = create_app()


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True,
    )
