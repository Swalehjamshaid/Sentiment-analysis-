# filename: app/routes/dashboard.py
from flask import Blueprint, render_template, jsonify, request
from sqlalchemy import func
from ..models import Company, Review

bp = Blueprint('dashboard', __name__)

@bp.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')

@bp.route('/api/kpis')
def kpis():
    total_reviews = Review.query.count()
    avg_rating = (Review.query.with_entities(func.avg(Review.rating)).scalar() or 0)
    pos = Review.query.filter_by(sentiment_category='Positive').count()
    neu = Review.query.filter_by(sentiment_category='Neutral').count()
    neg = Review.query.filter_by(sentiment_category='Negative').count()
    total = max(total_reviews, 1)
    return jsonify({
        'total_reviews': total_reviews,
        'avg_rating': round(avg_rating,2) if avg_rating else 0,
        'pos_rate': round(pos/total,2),
        'neu_rate': round(neu/total,2),
        'neg_rate': round(neg/total,2)
    })
