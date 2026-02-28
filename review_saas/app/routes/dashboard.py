# filename: app/routes/dashboard.py
from flask import Blueprint, render_template, jsonify, request
from datetime import datetime, timedelta

bp = Blueprint('dashboard', __name__)

@bp.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')

@bp.route('/api/kpis')
def kpis():
    data = {
        'total_reviews': 123,
        'avg_rating': 4.5,
        'pos_rate': 0.76,
        'neg_rate': 0.12
    }
    return jsonify(data)

@bp.route('/api/orders/series')
def orders_series():
    days = int(request.args.get('days', 14))
    today = datetime.utcnow().date()
    series = []
    for i in range(days):
        d = today - timedelta(days=days-1-i)
        series.append({'date': d.isoformat(), 'value': 50 + (i*3 % 17)})
    return jsonify(series)

@bp.route('/api/category-mix')
def category_mix():
    return jsonify({
        'Positive': 60,
        'Neutral': 25,
        'Negative': 15
    })

@bp.route('/api/activity')
def activity():
    limit = int(request.args.get('limit', 100))
    items = [{'id': i+1, 'action': 'review_ingested', 'ts': datetime.utcnow().isoformat()} for i in range(limit)]
    return jsonify(items)
