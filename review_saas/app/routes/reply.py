# filename: app/routes/reply.py
from flask import Blueprint, jsonify

bp = Blueprint('reply', __name__, url_prefix='/api')

@bp.route('/reply')
def reply():
    return jsonify({'status': 'stub'})
