from flask import Blueprint

health_bp = Blueprint('health', __name__)

@health_bp.route('/healthz', methods=['GET'])
def healthz():
    return "OK", 200
