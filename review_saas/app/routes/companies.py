# File: app/routes/companies.py

from sqlalchemy import func, extract, cast, Date
from datetime import datetime, timedelta

def get_dashboard_data(db: Session, company_id: int = None):
    # Base query
    query = db.query(Review)
    if company_id:
        query = query.filter(Review.company_id == company_id)
    
    reviews = query.all()
    total_reviews = len(reviews)
    
    # 1. Sentiment Trend Logic (Week-over-Week)
    # We group by the date truncated to the week to see changes over time
    last_4_weeks = datetime.now() - timedelta(weeks=4)
    
    trend_query = db.query(
        func.date_trunc('week', Review.review_date).label('week'),
        func.count(Review.id).filter(Review.rating >= 4).label('positive'),
        func.count(Review.id).filter(Review.rating <= 2).label('negative')
    ).filter(Review.review_date >= last_4_weeks)

    if company_id:
        trend_query = trend_query.filter(Review.company_id == company_id)
    
    weekly_trends = trend_query.group_by('week').order_by('week').all()

    # Formatting for Chart.js
    trend_labels = [row.week.strftime('%b %d') for row in weekly_trends]
    pos_trend_data = [row.positive for row in weekly_trends]
    neg_trend_data = [row.negative for row in weekly_trends]

    # ... (Keep existing Avg Rating, Heatmap, and Sentiment calculations) ...

    return {
        "metrics": {
            "total": total_reviews,
            "avg_rating": round(float(db.query(func.avg(Review.rating)).filter(Review.company_id == company_id).scalar() or 0), 1),
            "risk_score": 15, # Replace with dynamic logic
            "risk_level": "Low"
        },
        "sentiment_trend": {
            "labels": trend_labels,
            "positive": pos_trend_data,
            "negative": neg_trend_data
        },
        "sentiment": {
            "Positive": sum(pos_trend_data),
            "Neutral": total_reviews - (sum(pos_trend_data) + sum(neg_trend_data)),
            "Negative": sum(neg_trend_data)
        },
        "heatmap": {
            "labels": list(range(24)),
            "data": [0]*24 # Logic from previous step
        },
        "reviews": {
            "total": total_reviews,
            "data": [
                {
                    "id": r.id,
                    "review_date": r.review_date.isoformat(),
                    "rating": r.rating,
                    "reviewer_name": r.reviewer_name,
                    "text": r.text,
                    "sentiment_category": "Positive" if r.rating >= 4 else "Negative" if r.rating <= 2 else "Neutral"
                } for r in reviews[-5:]
            ]
        },
        "date_range": {"start": "2026-01-01", "end": "2026-02-24"}
    }
