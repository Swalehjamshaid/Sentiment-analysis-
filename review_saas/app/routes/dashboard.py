# review_saas/app/routes/dashboard.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime
from ..db import get_db
from ..models import Review, Company

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

def _apply_filters(q, company_id: int, start_date: str | None, end_date: str | None, sentiment: str | None, rating: int | None):
    q = q.filter(Review.company_id == company_id)
    if start_date:
        try: q = q.filter(Review.review_datetime >= datetime.fromisoformat(start_date))
        except: pass
    if end_date:
        try: q = q.filter(Review.review_datetime <= datetime.fromisoformat(end_date))
        except: pass
    if sentiment:
        q = q.filter(Review.sentiment_category == sentiment)
    if rating:
        q = q.filter(Review.rating == rating)
    return q

@router.get("/summary/{company_id}")
async def summary(
    company_id: int,
    start_date: str | None = None,
    end_date: str | None = None,
    sentiment: str | None = None,
    rating: int | None = None,
    db: Session = Depends(get_db)
):
    c = db.query(Company).get(company_id)
    if not c: raise HTTPException(status_code=404, detail="Not found")

    base = _apply_filters(db.query(Review), company_id, start_date, end_date, sentiment, rating)
    total = base.count() or 0
    avg_rating = base.with_entities(func.avg(Review.rating)).scalar() or 0
    pos = _apply_filters(db.query(Review), company_id, start_date, end_date, "Positive" if not sentiment else sentiment, rating)
    neu = _apply_filters(db.query(Review), company_id, start_date, end_date, "Neutral" if not sentiment else sentiment, rating)
    neg = _apply_filters(db.query(Review), company_id, start_date, end_date, "Negative" if not sentiment else sentiment, rating)

    pos_cnt = pos.count() if not sentiment else (total if sentiment == "Positive" else 0)
    neu_cnt = neu.count() if not sentiment else (total if sentiment == "Neutral" else 0)
    neg_cnt = neg.count() if not sentiment else (total if sentiment == "Negative" else 0)

    return {
        "total_reviews": total,
        "avg_rating": round(float(avg_rating), 2),
        "positive_pct": round((pos_cnt/total*100) if total else 0, 2),
        "neutral_pct": round((neu_cnt/total*100) if total else 0, 2),
        "negative_pct": round((neg_cnt/total*100) if total else 0, 2),
    }

@router.get("/trend/{company_id}")
async def trend(
    company_id: int,
    start_date: str | None = None,
    end_date: str | None = None,
    sentiment: str | None = None,
    rating: int | None = None,
    db: Session = Depends(get_db)
):
    q = _apply_filters(db.query(Review), company_id, start_date, end_date, sentiment, rating)
    q = q.filter(Review.review_datetime.isnot(None))
    q = q.with_entities(
        func.strftime("%Y-%m", Review.review_datetime).label("period"),
        func.avg(Review.rating),
        func.count(Review.id)
    ).group_by("period").order_by("period")
    return [{"period": p, "avg_rating": float(a or 0), "count": int(c)} for p, a, c in q]

@router.get("/keywords/{company_id}")
async def keywords(
    company_id: int,
    start_date: str | None = None,
    end_date: str | None = None,
    sentiment: str | None = None,
    rating: int | None = None,
    db: Session = Depends(get_db)
):
    import json
    from collections import Counter
    q = _apply_filters(db.query(Review), company_id, start_date, end_date, sentiment, rating)
    kws = []
    for r in q.all():
        if r.keywords:
            kws.extend(json.loads(r.keywords))
    ctr = Counter(kws)
    return [{"keyword": k, "count": v} for k, v in ctr.most_common(50)]

# (Export endpoint remains from your previous version)
