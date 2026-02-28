# filename: app/__init__.py
from flask import Flask
from .core.config import Settings
from .db import init_db

def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = Settings().secret_key

    # init db
    init_db(app)

    # register blueprints
    from .routes.auth import bp as auth_bp
    from .routes.dashboard import bp as dashboard_bp
    from .routes.companies import bp as companies_bp
    from .routes.insights import bp as insights_bp
    from .routes.activity import bp as activity_bp
    from .routes.reviews import bp as reviews_bp
    from .routes.reports import bp as reports_bp
    from .routes.reply import bp as reply_bp
    from .routes.admin import bp as admin_bp
    from .routes.maps_routes import bp as maps_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(companies_bp)
    app.register_blueprint(insights_bp)
    app.register_blueprint(activity_bp)
    app.register_blueprint(reviews_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(reply_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(maps_bp)

    @app.route('/')
    def index():
        from flask import render_template
        return render_template('index.html')

    return app
