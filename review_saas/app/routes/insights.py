
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import datetime, timedelta

from app.db import get_db
from app.models import Company, Review

router = APIRouter(prefix="/api", tags=["insights"])

def _parse_date(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    for fmt in ("%Y-%m-%d",):
        try:
            return datetime.strptime(s, fmt)
        except Exception:
            pass
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return None

@router.get("/insights")
def get_insights(
    company_id: int = Query(..., alias="company_id"),
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    q = db.query(Review).filter(Review.company_id == company_id)
    start_dt = _parse_date(start); end_dt = _parse_date(end)
    if start_dt:
        q = q.filter(Review.review_date >= start_dt)
    if end_dt:
        if end_dt.hour == 0 and end_dt.minute == 0 and end_dt.second == 0:
            q = q.filter(Review.review_date < (end_dt + timedelta(days=1)))
        else:
            q = q.filter(Review.review_date <= end_dt)
    reviews: List[Review] = q.all()

    if not reviews:
        return {
            "insights": "No reviews available for analysis in the selected period.",
            "recommendations": [
                "Expand date range and re-run analysis.",
                "Trigger a reviews sync to make sure the latest data is available."
            ]
        }

    total = len(reviews)
    ratings = [float(r.rating or 0.0) for r in reviews if r.rating is not None]
    avg = round(sum(ratings)/len(ratings), 2) if ratings else 0.0

    pos = neu = neg = 0
    for r in reviews:
        cat = (r.sentiment_category or '').lower()
        if cat.startswith('pos'):
            pos += 1
        elif cat.startswith('neg'):
            neg += 1
        else:
            neu += 1

    share_pos = round((pos/total)*100, 1) if total else 0.0
    share_neg = round((neg/total)*100, 1) if total else 0.0
    share_neu = round((neu/total)*100, 1) if total else 0.0

    insights = (
        f"Based on {total} reviews, the average rating is {avg}. "
        f"Sentiment split: {share_pos}% positive, {share_neu}% neutral, {share_neg}% negative. "
        "Focus on reducing negative drivers while reinforcing strengths cited in positive feedback."
    )

    recommendations = []
    if share_neg >= 20:
        recommendations.append({
            "title": "Reduce negative experience drivers",
            "desc": "Identify top complaint themes and assign owners to remediate within 2 weeks.",
            "priority": "high"
        })
    if avg < 4.0:
        recommendations.append({
            "title": "Boost quality & responsiveness",
            "desc": "Publish 3 templated responses and commit to < 4h response time on low-rated reviews.",
            "priority": "medium"
        })
    if share_pos >= 50:
        recommendations.append({
            "title": "Amplify strengths",
            "desc": "Highlight top positive themes in marketing and product pages.",
            "priority": "low"
        })

    if not recommendations:
        recommendations = [
            {
                "title": "Maintain current performance",
                "desc": "Monitor sentiment weekly and address any emerging negative themes.",
                "priority": "low"
            }
        ]

    return {
        "insights": insights,
        "recommendations": recommendations
    }
