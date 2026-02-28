# filename: app/routes/activity.py
from flask import Blueprint, jsonify

bp = Blueprint('activity', __name__, url_prefix='/api')

@bp.route('/export/activity.csv')
def export_activity_csv():
    # Placeholder response
    return jsonify({'detail': 'CSV export endpoint placeholder'})

@bp.route('/export/activity.xlsx')
def export_activity_xlsx():
    return jsonify({'detail': 'XLSX export endpoint placeholder'})
