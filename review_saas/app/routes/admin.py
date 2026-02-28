# filename: app/routes/admin.py
from flask import Blueprint, jsonify

bp = Blueprint('admin', __name__, url_prefix='/api')

@bp.route('/admin/health')
def admin_health():
    return jsonify({'status': 'healthy'})
