# filename: app/routes/reports.py
from flask import Blueprint, jsonify

bp = Blueprint('reports', __name__, url_prefix='/api')

@bp.route('/reports/summary')
def reports_summary():
    return jsonify({'summary': 'ok'})
