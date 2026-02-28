# filename: app/routes/reviews.py
from flask import Blueprint, jsonify

bp = Blueprint('reviews', __name__, url_prefix='/api')

@bp.route('/reviews')
def list_reviews():
    return jsonify([])
