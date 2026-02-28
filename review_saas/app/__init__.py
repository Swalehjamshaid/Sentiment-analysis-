# filename: app/__init__.py
"""App factory with lazy imports; registers blueprints and secures defaults."""

def create_app():
    from flask import Flask
    from flask import redirect, request
    from flask_cors import CORS
    from .core.config import Settings
    from .db import init_db

    app = Flask(__name__)
    settings = Settings()
    app.config['SECRET_KEY'] = settings.secret_key

    # DB
    init_db(app)

    # CORS (tighten for production)
    CORS(app, supports_credentials=True)

    # Blueprints
    from .routes.auth import bp as auth_bp
    from .routes.dashboard import bp as dashboard_bp
    from .routes.companies import bp as companies_bp
    from .routes.reviews import bp as reviews_bp
    from .routes.reports import bp as reports_bp
    from .routes.admin import bp as admin_bp

    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(companies_bp, url_prefix='/companies')
    app.register_blueprint(reviews_bp, url_prefix='/api')
    app.register_blueprint(reports_bp, url_prefix='/api')
    app.register_blueprint(admin_bp, url_prefix='/api')

    @app.route('/')
    def index():
        from flask import render_template
        return render_template('index.html')

    return app
