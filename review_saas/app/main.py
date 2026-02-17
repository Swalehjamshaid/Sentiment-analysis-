import os
from flask import Flask, redirect, url_for
from app.core.settings import settings_dict
from app.routes.auth import auth_bp
from app.routes.companies import companies_bp
from app.routes.dashboard import dashboard_bp
from app.db import db_session

def create_app():
    app = Flask(__name__, template_folder='../templates')
    
    # Requirement 10: Load Configuration
    app.config.update(settings_dict())
    app.secret_key = app.config.get("SECRET_KEY")

    # Registering Requirement-based Blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(companies_bp)
    app.register_blueprint(dashboard_bp)

    @app.context_processor
    def inject_globals():
        return {"GOOGLE_MAPS_API_KEY": app.config.get("GOOGLE_MAPS_API_KEY")}

    @app.teardown_appcontext
    def shutdown_session(exception=None):
        db_session.remove()

    @app.route('/')
    def root():
        return redirect(url_for('dashboard.view_dashboard'))

    return app

if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
