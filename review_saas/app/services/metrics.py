
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime
from app.models import Review

def build_kpi_for_dashboard(db: Session, company_id: int, start_date: datetime, end_date: datetime):
    reviews = db.query(Review).filter(
        Review.company_id == company_id,
        Review.review_date.between(start_date, end_date)
    ).all()

    count = len(reviews)
    if count == 0:
        return {"avg_rating": 0, "review_count": 0, "sentiment_score": 0, "pos": 0, "neu": 0, "neg": 0}

    avg_rating = round(sum(r.rating for r in reviews if r.rating) / count, 1)
    pos = len([r for r in reviews if r.sentiment_category == 'Positive'])
    neu = len([r for r in reviews if r.sentiment_category == 'Neutral'])
    neg = len([r for r in reviews if r.sentiment_category == 'Negative'])

    return {
        "avg_rating": avg_rating,
        "review_count": count,
        "sentiment_score": round(sum((r.sentiment_score or 0) for r in reviews) / count, 2),
        "pos": int((pos / count) * 100),
        "neu": int((neu / count) * 100),
        "neg": int((neg / count) * 100),
        "avg_rating_delta": "+0%",
        "review_growth": "+0%",
        "response_rate": "0%",
        "avg_response_time": "0h"
    }
