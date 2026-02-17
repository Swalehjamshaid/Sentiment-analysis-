from flask import Blueprint

health_bp = Blueprint('health', __name__)

@health_bp.route('/healthz', methods=['GET'])
def healthz():
    """
    Health check endpoint required by Railway.
    Returns HTTP 200 OK immediately.
    """
    return "OK", 200
