from flask import Blueprint

health_bp = Blueprint("health", __name__)

@health_bp.route("/healthz", methods=["GET"])
def health_check():
    """
    Railway healthcheck endpoint.
    Must ALWAYS return 200.
    No DB calls.
    No auth.
    No external services.
    """
    return "OK", 200
