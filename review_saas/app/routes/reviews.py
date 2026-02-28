# filename: app/routes/reviews.py
from flask import Blueprint, jsonify, request
from datetime import datetime, timezone
from ..db import db
from ..models import Company, Review
from ..services.sentiment import star_to_category, text_sentiment
from ..services.replies import generate_reply

bp = Blueprint('reviews', __name__)

@bp.route('/reviews/fetch', methods=['POST'])
def fetch_reviews():
    data = request.get_json() or {}
    company_id = data.get('company_id')
    limit = min(int(data.get('limit', 100)), 500)
    # NOTE: For MVP, we simulate fetch; integrate googlemaps Place Reviews if available.
    comp = Company.query.get_or_404(company_id)
    # Simulated review
    sample = Review(company_id=comp.id, external_id=f'sim-{datetime.now().timestamp()}',
                    text='Great service and fast delivery!', rating=5, review_date=datetime.now(timezone.utc),
                    reviewer_name='John Doe', reviewer_avatar='')
    sample.sentiment_category = star_to_category(sample.rating)
    sample.sentiment_score = text_sentiment(sample.text).get('compound', 0.0)
    db.session.add(sample)
    db.session.commit()
    return jsonify({'status':'ok', 'inserted':1})

@bp.route('/reviews/<int:company_id>')
def list_reviews(company_id):
    items = Review.query.filter_by(company_id=company_id).order_by(Review.review_date.desc()).limit(100).all()
    return jsonify([
        {
            'id':r.id,
            'rating': r.rating,
            'text': r.text[:5000] if r.text else None,
            'date': r.review_date.isoformat() if r.review_date else None,
            'sentiment': r.sentiment_category,
            'score': r.sentiment_score,
            'suggested_reply': generate_reply(r.rating, r.text)
        } for r in items
    ])
