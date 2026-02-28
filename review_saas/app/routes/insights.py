# filename: app/routes/insights.py
from flask import Blueprint, jsonify

bp = Blueprint('insights', __name__, url_prefix='/api')

@bp.route('/insights')
def get_insights():
    return jsonify({'top_themes': ['support', 'battery', 'delivery'], 'sentiment': {'pos': 70, 'neg': 12, 'neu': 18}})
