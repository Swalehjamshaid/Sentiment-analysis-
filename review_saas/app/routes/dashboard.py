# File 5: dashboard.py

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import Company, Review

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

@router.get("/summary/{company_id}")
def company_summary(company_id: int, db: Session = Depends(get_db)):
    company = db.query(Company).filter_by(id=company_id).first()
    if not company:
        return {"error": "Company not found"}

    reviews = db.query(Review).filter_by(company_id=company_id).all()
    total = len(reviews)
    positive = sum(1 for r in reviews if r.sentiment_category=="Positive")
    neutral = sum(1 for r in reviews if r.sentiment_category=="Neutral")
    negative = sum(1 for r in reviews if r.sentiment_category=="Negative")
    avg_rating = sum([r.rating for r in reviews])/total if total else 0
    return {
        "company_name": company.name,
        "total_reviews": total,
        "avg_rating": avg_rating,
        "positive_pct": positive/total*100 if total else 0,
        "neutral_pct": neutral/total*100 if total else 0,
        "negative_pct": negative/total*100 if total else 0,
        "recent_reviews": [r.text for r in reviews[-10:]]
    }
