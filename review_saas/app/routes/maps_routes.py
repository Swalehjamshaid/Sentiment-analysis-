# filename: app/routes/maps_routes.py
from flask import Blueprint, jsonify

bp = Blueprint('maps', __name__, url_prefix='/google')

@bp.route('/health')
def health():
    return jsonify({'google_api': 'ok'})

@bp.route('/sync')
def sync():
    return jsonify({'synced': True})
