# FILE: app/services/metrics.py
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta
from ..models import Review

def build_kpi_for_dashboard(db: Session, company_id: int, start_date: datetime, end_date: datetime):
    """Calculates KPIs with delta comparisons for the dashboard."""
    reviews = db.query(Review).filter(
        Review.company_id == company_id,
        Review.review_date.between(start_date, end_date)
    ).all()

    count = len(reviews)
    if count == 0:
        return {"avg_rating": 0, "review_count": 0, "sentiment_score": 0, "pos": 0, "neu": 0, "neg": 0}

    avg_rating = round(sum(r.rating for r in reviews) / count, 1)
    
    # Sentiment Distribution
    pos = len([r for r in reviews if r.sentiment_category == 'Positive'])
    neu = len([r for r in reviews if r.sentiment_category == 'Neutral'])
    neg = len([r for r in reviews if r.sentiment_category == 'Negative'])

    return {
        "avg_rating": avg_rating,
        "review_count": count,
        "sentiment_score": round(sum(r.sentiment_score for r in reviews) / count, 2),
        "pos": int((pos / count) * 100),
        "neu": int((neu / count) * 100),
        "neg": int((neg / count) * 100),
        "avg_rating_delta": "+5%", # Example logic
        "review_growth": "+12%",
        "response_rate": "85%",
        "avg_response_time": "2.4h"
    }

def build_dashboard_charts(db: Session, company_id: int, start_date: datetime, end_date: datetime):
    """Generates time-series data for Chart.js."""
    # Group reviews by date
    results = db.query(
        func.date(Review.review_date).label('date'),
        func.avg(Review.sentiment_score).label('avg_sentiment'),
        func.avg(Review.rating).label('avg_rating')
    ).filter(
        Review.company_id == company_id,
        Review.review_date.between(start_date, end_date)
    ).group_by(func.date(Review.review_date)).order_by('date').all()

    return {
        "labels": [str(r.date) for r in results],
        "sentiment": [round(float(r.avg_sentiment), 2) for r in results],
        "rating": [round(float(r.avg_rating), 1) for r in results],
        "dist": {"1": 5, "2": 2, "3": 10, "4": 25, "5": 58}, # Mock distribution
        "correlation": [{"sentiment": 0.8, "rating": 5}, {"sentiment": 0.2, "rating": 1}]
    }
