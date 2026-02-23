# FILE: app/routes/dashboard.py

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional, List, Tuple, Dict
from datetime import datetime
from collections import defaultdict

from ..db import get_db
from ..models import Company, Review

# IMPORTANT:
# This router exposes ONLY API endpoints consumed by dashboard.html.
# The dashboard page itself is rendered in main.py (UI route /dashboard).

router = APIRouter(prefix="/api", tags=["dashboard"])

# -----------------------------
# Helpers
# -----------------------------
def _parse_date(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    # Accept 'YYYY-MM-DD' or ISO strings
    try:
        # Try strict date only first
        return datetime.strptime(s, "%Y-%m-%d")
    except Exception:
        try:
            return datetime.fromisoformat(s)
        except Exception:
            return None

def _apply_date_filter(query, start: Optional[str], end: Optional[str]):
    start_dt = _parse_date(start)
    end_dt = _parse_date(end)
    if start_dt:
        query = query.filter(Review.review_date >= start_dt)
    if end_dt:
        # Include the entire end day if time not supplied
        if end_dt.hour == 0 and end_dt.minute == 0 and end_dt.second == 0:
            # add one day, then use < next day
            from datetime import timedelta
            query = query.filter(Review.review_date < (end_dt + timedelta(days=1)))
        else:
            query = query.filter(Review.review_date <= end_dt)
    return query

def calc_risk(avg_rating: float, total: int) -> float:
    """
    Example risk function:
    - Lower average ratings increase risk.
    - More review volume increases the impact slightly.
    """
    if avg_rating is None:
        avg_rating = 0.0
    base = 100 - (avg_rating * 20)  # 0..5 -> 100..0
    volume_penalty = min(total / 50.0, 20)  # cap at +20
    score = max(0.0, min(100.0, base + volume_penalty))
    return round(score, 2)

def risk_level(score: float) -> str:
    # Capitalized for compatibility with existing UI conditions
    if score >= 70:
        return "High"
    if score >= 40:
        return "Medium"
    return "Low"

# ============================================================
# 1) COMPANIES (Dropdown)
# ============================================================
@router.get("/companies")
def get_companies(db: Session = Depends(get_db)):
    """
    Returns active companies for the dashboard selector.
    """
    # Assumes Company has a 'status' column == 'active'
    return db.query(Company).filter(Company.status == "active").all()

# ============================================================
# 2) METRICS (Date-filtered)
#    Response matches dashboard.html expectations.
# ============================================================
@router.get("/metrics")
def get_dashboard_metrics(
    company_id: int = Query(..., alias="company_id"),
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    # Validate company
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    query = db.query(Review).filter(Review.company_id == company_id)
    query = _apply_date_filter(query, start, end)

    total = query.count()
    avg_rating = query.with_entities(func.avg(Review.rating)).scalar() or 0.0
    risk = calc_risk(avg_rating, total)
    level = risk_level(risk)

    return {
        "total": total,
        "avg_rating": round(float(avg_rating), 2),
        "risk_score": risk,
        "risk_level": level,
    }

# ============================================================
# 3) RATING TREND (time series; average rating by day)
# ============================================================
@router.get("/trend")
def get_trend(
    company_id: int = Query(..., alias="company_id"),
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    q = db.query(Review).filter(Review.company_id == company_id)
    q = _apply_date_filter(q, start, end)

    # Group by day; compatible across most DBs using DATE() cast
    day_col = func.date(Review.review_date)
    rows: List[Tuple] = (
        q.with_entities(day_col.label("d"), func.avg(Review.rating).label("avg"))
         .group_by(day_col)
         .order_by(day_col.asc())
         .all()
    )

    labels = []
    data = []
    for d, a in rows:
        # d may already be a date-like; cast to string
        labels.append(str(d))
        data.append(round(float(a or 0.0), 2))

    return {"labels": labels, "data": data}

# ============================================================
# 4) SENTIMENT BREAKDOWN
#    Returns counts for pos/neu/neg.
#    Uses Review.sentiment_category if available; otherwise infers from rating.
# ============================================================
@router.get("/sentiment")
def get_sentiment(
    company_id: int = Query(..., alias="company_id"),
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    q = db.query(Review).filter(Review.company_id == company_id)
    q = _apply_date_filter(q, start, end)

    # Try DB-side sentiment_category aggregation if column exists
    pos = neu = neg = 0

    try:
        rows: List[Tuple] = (
            q.with_entities(Review.sentiment_category, func.count(Review.id))
             .group_by(Review.sentiment_category)
             .all()
        )
        # Expect sentiment_category values like 'pos','neu','neg' or similar
        for cat, cnt in rows:
            if not cat:
                continue
            c = str(cat).lower()
            if c.startswith("pos"):
                pos += cnt
            elif c.startswith("neu"):
                neu += cnt
            elif c.startswith("neg"):
                neg += cnt
    except Exception:
        # Fallback: infer from rating if sentiment_category not available
        for r in q.all():
            if r.rating is None:
                neu += 1
            elif r.rating >= 4:
                pos += 1
            elif r.rating <= 2:
                neg += 1
            else:
                neu += 1

    return {"pos": int(pos), "neu": int(neu), "neg": int(neg)}

# ============================================================
# 5) REVENUE PREDICTION (simple placeholder)
#    Replace with your ML service when ready.
# ============================================================
@router.get("/revenue/predict")
def revenue_predict(
    company_id: int = Query(..., alias="company_id"),
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    q = db.query(Review).filter(Review.company_id == company_id)
    q = _apply_date_filter(q, start, end)

    # Very simple heuristic placeholder:
    # - Bucket by month; use count of reviews * scaled avg rating as proxy.
    rows = q.with_entities(Review.review_date, Review.rating).all()
    monthly = defaultdict(lambda: {"count": 0, "sum_rating": 0.0})

    for dt, rating in rows:
        if not dt:
            continue
        key = dt.strftime("%Y-%m")  # e.g., 2026-02
        monthly[key]["count"] += 1
        monthly[key]["sum_rating"] += float(rating or 0.0)

    # Sort by month ascending and take last 6 periods
    months_sorted = sorted(monthly.keys())
    months_sorted = months_sorted[-6:] if months_sorted else []

    labels = []
    data = []
    for key in months_sorted:
        ym = datetime.strptime(key, "%Y-%m")
        labels.append(ym.strftime("%b %Y"))
        cnt = monthly[key]["count"]
        avg = (monthly[key]["sum_rating"] / cnt) if cnt else 0.0
        # Proxy revenue = base * count * normalized(avg)
        proxy = max(0.0, cnt * (avg / 5.0) * 100.0)
        data.append(round(proxy, 2))

    # Fallback if no data
    if not labels:
        labels = ["Jan", "Feb", "Mar", "Apr", "May", "Jun"]
        data = [0, 0, 0, 0, 0, 0]

    return {"labels": labels, "data": data}

# ============================================================
# 6) SYNC REVIEWS (trigger)
# ============================================================
@router.post("/reviews/sync")
def sync_reviews(
    company_id: int = Query(..., alias="company_id"),
    db: Session = Depends(get_db),
):
    """
    Trigger a review sync for this company.
    Replace the body with your actual ingestion pipeline / background task.
    """
    # Example: return immediately and let a background task run:
    # task_id = start_sync_job(company_id)
    # return {"ok": True, "task_id": task_id, "message": "Sync started"}

    # Placeholder success:
    return {"ok": True, "message": "Reviews synced successfully"}
