"""
Application entry point.
Creates the Flask app, injects template globals, and runs the dev server when executed directly.
"""

from flask import Flask
from app.core.settings import settings_dict
from app.routes.auth import auth_bp
from app.routes.companies import companies_bp
from app.routes.dashboard import dashboard_bp
from app.routes.reviews import reviews_bp
from app.routes.recipes import recipes_bp
from app.routes.reports import reports_bp


def create_app() -> Flask:
    app = Flask(__name__)
    # Load config from environment via settings
    app.config.update(settings_dict())

    # Blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(companies_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(reviews_bp)
    app.register_blueprint(recipes_bp)
    app.register_blueprint(reports_bp)

    # Template globals (so base.html can access GOOGLE_MAPS_API_KEY easily)
    @app.context_processor
    def inject_globals():
        return {
            "GOOGLE_MAPS_API_KEY": app.config.get("GOOGLE_MAPS_API_KEY", ""),
        }

    # Root → dashboard
    @app.route("/")
    def root():
        from flask import redirect, url_for
        return redirect(url_for("dashboard.view_dashboard"))

    return app


# Dev server
if __name__ == "__main__":
    app = create_app()
    app.run(
        host="0.0.0.0",
        port=int(app.config.get("PORT", 5000)),
        debug=bool(app.config.get("DEBUG", True)),
    )
