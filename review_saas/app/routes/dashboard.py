# FILE: app/routes/dashboard.py

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, text
from typing import Optional, List, Tuple, Dict, Any
from datetime import datetime
from collections import defaultdict
import csv
import io
import math

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
    # Placeholder success:
    return {"ok": True, "message": "Reviews synced successfully"}

# ============================================================
# 7) NEW: SOURCES BREAKDOWN (pie / doughnut)
# ============================================================
@router.get("/sources")
def get_sources_breakdown(
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

    # If Review.source exists, aggregate by it; else return "unknown"
    labels: List[str] = []
    data: List[int] = []

    try:
        rows: List[Tuple[str, int]] = (
            q.with_entities(Review.source, func.count(Review.id))
             .group_by(Review.source)
             .all()
        )
        # Normalize nulls to "unknown"
        buckets: Dict[str, int] = defaultdict(int)
        for src, cnt in rows:
            key = (src or "unknown").strip() or "unknown"
            buckets[key] += cnt
        labels = list(buckets.keys())
        data = [int(buckets[k]) for k in labels]
    except Exception:
        total = q.count()
        labels = ["unknown"]
        data = [int(total)]

    return {"labels": labels, "data": data}

# ============================================================
# 8) NEW: HEATMAP (hour-of-day histogram 0..23)
# ============================================================
@router.get("/heatmap")
def get_heatmap(
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

    # DB-agnostic approach: pull timestamps and bucket in Python
    hours = [0] * 24
    for (dt,) in q.with_entities(Review.review_date).all():
        if isinstance(dt, datetime):
            hours[dt.hour] += 1

    return {"labels": list(range(24)), "data": hours}

# ============================================================
# 9) NEW: REVIEWS TABLE (paginated + search + sort)
# ============================================================
@router.get("/reviews")
def get_reviews_table(
    company_id: int = Query(..., alias="company_id"),
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(25, ge=1, le=200),
    search: Optional[str] = Query(None, min_length=1),
    sort: str = Query("review_date", regex=r"^(review_date|rating|source)$"),
    order: str = Query("desc", regex=r"^(asc|desc)$"),
    db: Session = Depends(get_db),
):
    """
    Returns paginated reviews, shaped for dashboard table.
    """
    # Validate
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    q = db.query(Review).filter(Review.company_id == company_id)
    q = _apply_date_filter(q, start, end)

    if search:
        s = f"%{search.strip()}%"
        # Try searching in title/text/author/source when present
        filters = []
        for col in ("title", "text", "author", "source"):
            if hasattr(Review, col):
                filters.append(getattr(Review, col).ilike(s))
        if filters:
            from sqlalchemy import or_
            q = q.filter(or_(*filters))

    total = q.count()

    # Sorting
    sort_col = getattr(Review, sort)
    q = q.order_by(sort_col.desc() if order == "desc" else sort_col.asc())

    # Pagination
    offset = (page - 1) * limit
    rows: List[Review] = q.offset(offset).limit(limit).all()

    def to_dict(r: Review) -> Dict[str, Any]:
        return {
            "id": getattr(r, "id", None),
            "review_date": getattr(r, "review_date", None).isoformat() if getattr(r, "review_date", None) else None,
            "rating": float(getattr(r, "rating", 0.0) or 0.0),
            "title": getattr(r, "title", None) if hasattr(r, "title") else None,
            "text": getattr(r, "text", None) if hasattr(r, "text") else None,
            "author": getattr(r, "author", None) if hasattr(r, "author") else None,
            "source": getattr(r, "source", None) if hasattr(r, "source") else None,
            "url": getattr(r, "url", None) if hasattr(r, "url") else None,
            "sentiment_category": getattr(r, "sentiment_category", None) if hasattr(r, "sentiment_category") else None,
            "keywords": getattr(r, "keywords", None) if hasattr(r, "keywords") else None,
        }

    data = [to_dict(r) for r in rows]

    return {
        "page": page,
        "limit": limit,
        "total": total,
        "pages": math.ceil(total / limit) if limit else 1,
        "data": data,
    }

# ============================================================
# 10) NEW: KEYWORDS (top terms)
#       - Uses Review.keywords if available (csv/array-like in string).
#       - Else extracts simple tokens from Review.text (basic, DB-agnostic).
# ============================================================
@router.get("/keywords")
def get_top_keywords(
    company_id: int = Query(..., alias="company_id"),
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    top_n: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    q = db.query(Review).filter(Review.company_id == company_id)
    q = _apply_date_filter(q, start, end)

    buckets: Dict[str, int] = defaultdict(int)

    # Prefer structured keywords column if available
    if hasattr(Review, "keywords"):
        for kw in q.with_entities(Review.keywords).all():
            val = (kw[0] or "").strip()
            if not val:
                continue
            # Handle comma/semicolon separation
            parts = [p.strip().lower() for p in val.replace(";", ",").split(",") if p.strip()]
            for p in parts:
                buckets[p] += 1
    else:
        # Fallback: naive tokenization from text
        import re
        stop = set([
            "the","and","a","an","is","it","to","of","in","on","for","with","this","that",
            "i","we","you","they","was","were","are","be","at","as","by","from","or","not",
            "very","but","so","if","out","up","down","over","under","than","then","too","also",
        ])
        tokens_re = re.compile(r"[A-Za-z]{3,}")
        for txt, in q.with_entities(Review.text).all():
            text_val = (txt or "")
            for tok in tokens_re.findall(text_val.lower()):
                if tok in stop:
                    continue
                buckets[tok] += 1

    items = sorted(buckets.items(), key=lambda x: x[1], reverse=True)[:top_n]
    labels = [k for k, _ in items]
    data = [int(v) for _, v in items]
    return {"labels": labels, "data": data}

# ============================================================
# 11) NEW: ALERTS (simple heuristic)
#       - Detect recent avg rating vs previous period drop/spike.
# ============================================================
@router.get("/alerts")
def get_alerts(
    company_id: int = Query(..., alias="company_id"),
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    window_days: int = Query(14, ge=7, le=90),
    db: Session = Depends(get_db),
):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    # Determine time windows from filters or relative to available data
    base_q = db.query(Review).filter(Review.company_id == company_id)
    base_q = _apply_date_filter(base_q, start, end)

    # Get bounds
    min_dt, max_dt = base_q.with_entities(
        func.min(Review.review_date), func.max(Review.review_date)
    ).first() or (None, None)

    if not min_dt or not max_dt:
        return {"alerts": []}

    from datetime import timedelta
    recent_start = max_dt - timedelta(days=window_days)
    prev_start = recent_start - timedelta(days=window_days)
    prev_end = recent_start

    recent_q = base_q.filter(Review.review_date >= recent_start)
    prev_q = base_q.filter(Review.review_date >= prev_start, Review.review_date < prev_end)

    recent_avg = float(recent_q.with_entities(func.avg(Review.rating)).scalar() or 0.0)
    prev_avg = float(prev_q.with_entities(func.avg(Review.rating)).scalar() or 0.0)

    recent_cnt = int(recent_q.count())
    prev_cnt = int(prev_q.count())

    alerts: List[Dict[str, Any]] = []

    delta = recent_avg - prev_avg
    # Significant drop
    if delta <= -0.5 and recent_cnt >= 10:
        alerts.append({
            "type": "warning",
            "title": "Rating drop detected",
            "message": f"Average rating fell by {abs(round(delta, 2))} in last {window_days} days.",
            "recent_avg": round(recent_avg, 2),
            "previous_avg": round(prev_avg, 2),
            "recent_count": recent_cnt,
            "previous_count": prev_cnt,
        })
    # Significant increase
    if delta >= 0.5 and recent_cnt >= 10:
        alerts.append({
            "type": "success",
            "title": "Rating improvement",
            "message": f"Average rating increased by {round(delta, 2)} in last {window_days} days.",
            "recent_avg": round(recent_avg, 2),
            "previous_avg": round(prev_avg, 2),
            "recent_count": recent_cnt,
            "previous_count": prev_cnt,
        })

    # Volume spike
    if prev_cnt and recent_cnt >= prev_cnt * 2 and recent_cnt >= 20:
        alerts.append({
            "type": "info",
            "title": "Volume spike",
            "message": f"Review volume doubled ({recent_cnt} vs {prev_cnt}).",
            "recent_count": recent_cnt,
            "previous_count": prev_cnt,
        })

    return {"alerts": alerts}

# ============================================================
# 12) NEW: EXPORT (CSV) with date filters
# ============================================================
@router.get("/export")
def export_reviews_csv(
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
    q = q.order_by(Review.review_date.desc())

    # Prepare CSV in-memory
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    # Header (include common fields; tolerate missing attrs)
    header = [
        "id", "review_date", "rating", "title", "text", "author",
        "source", "url", "sentiment_category", "keywords"
    ]
    writer.writerow(header)

    for r in q.all():
        row = [
            getattr(r, "id", None),
            getattr(r, "review_date", None).isoformat() if getattr(r, "review_date", None) else "",
            getattr(r, "rating", "") if getattr(r, "rating", None) is not None else "",
            getattr(r, "title", "") if hasattr(r, "title") else "",
            getattr(r, "text", "") if hasattr(r, "text") else "",
            getattr(r, "author", "") if hasattr(r, "author") else "",
            getattr(r, "source", "") if hasattr(r, "source") else "",
            getattr(r, "url", "") if hasattr(r, "url") else "",
            getattr(r, "sentiment_category", "") if hasattr(r, "sentiment_category") else "",
            getattr(r, "keywords", "") if hasattr(r, "keywords") else "",
        ]
        writer.writerow(row)

    buffer.seek(0)
    filename = f"reviews_company_{company_id}.csv"
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )
