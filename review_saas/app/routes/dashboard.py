# FILE: app/routes/dashboard.py
"""
Dashboard API endpoints consumed by dashboard.html

This router is aligned with your models and existing routes:
- Uses Review fields that actually exist (no .source/.title/.author/.url).
- Provides metrics, trend, sentiment, sources (as 'google' bucket), heatmap,
  paginated reviews, keywords, alerts, CSV export, and a sync trigger.
- Date parsing accepts YYYY-MM-DD or ISO strings; end-date is inclusive by day.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional, List, Tuple, Dict, Any
from datetime import datetime, timedelta
from collections import defaultdict
import csv
import io
import math
import logging

from ..db import get_db
from ..models import Company, Review

router = APIRouter(prefix="/api", tags=["dashboard"])

# ─────────────────────────────────────────────────────────────
# Logger (handy for API diagnostics in container logs)
# ─────────────────────────────────────────────────────────────
logger = logging.getLogger("dashboard")
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    logger.addHandler(_h)
logger.setLevel(logging.INFO)

# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────
def _parse_date(s: Optional[str]) -> Optional[datetime]:
    """Parse 'YYYY-MM-DD' or ISO string → naive datetime. Returns None on failure."""
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d")
    except Exception:
        try:
            return datetime.fromisoformat(s)
        except Exception:
            return None


def _apply_date_filter(query, start: Optional[str], end: Optional[str]):
    """
    Inclusive time window on Review.review_date.
    If end has 00:00:00, consider full end-day by adding +1 day with '<'.
    """
    start_dt = _parse_date(start)
    end_dt = _parse_date(end)
    if start_dt:
        query = query.filter(Review.review_date >= start_dt)
    if end_dt:
        if end_dt.hour == 0 and end_dt.minute == 0 and end_dt.second == 0:
            query = query.filter(Review.review_date < (end_dt + timedelta(days=1)))
        else:
            query = query.filter(Review.review_date <= end_dt)
    return query


def _calc_risk(avg_rating: float, total: int) -> float:
    """
    Heuristic risk: lower ratings + higher volume → higher risk.
    5★ → 0 risk; 0★ → 100 risk; volume can add up to +20.
    """
    if avg_rating is None:
        avg_rating = 0.0
    base = 100 - (avg_rating * 20)  # rating 0..5 → 100..0
    volume_penalty = min(total / 50.0, 20)  # cap
    score = max(0.0, min(100.0, base + volume_penalty))
    return round(score, 2)


def _risk_level(score: float) -> str:
    if score >= 70:
        return "High"
    if score >= 40:
        return "Medium"
    return "Low"


# ============================================================
# 1) COMPANIES (Dropdown for dashboard)
# ============================================================
@router.get("/companies")
def get_companies(db: Session = Depends(get_db)):
    """
    Returns active companies for the dashboard selector.

    NOTE: The UI should select a company_id from this response
    and use it to call the rest endpoints below.
    """
    return db.query(Company).filter(Company.status == "active").order_by(Company.created_at.desc()).all()


# ============================================================
# 2) METRICS (KPI cards)
# ============================================================
@router.get("/metrics")
def get_dashboard_metrics(
    company_id: int = Query(..., alias="company_id"),
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(404, "Company not found")

    q = db.query(Review).filter(Review.company_id == company_id)
    q = _apply_date_filter(q, start, end)

    total = q.count()
    avg_rating = float(q.with_entities(func.avg(Review.rating)).scalar() or 0.0)
    risk = _calc_risk(avg_rating, total)
    level = _risk_level(risk)

    return {
        "total": total,
        "avg_rating": round(avg_rating, 2),
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
        raise HTTPException(404, "Company not found")

    q = db.query(Review).filter(Review.company_id == company_id)
    q = _apply_date_filter(q, start, end)

    day_col = func.date(Review.review_date)
    rows: List[Tuple] = (
        q.with_entities(day_col.label("d"), func.avg(Review.rating).label("avg"))
         .group_by(day_col)
         .order_by(day_col.asc())
         .all()
    )

    labels: List[str] = []
    data: List[float] = []
    for d, a in rows:
        labels.append(str(d))
        data.append(round(float(a or 0.0), 2))

    return {"labels": labels, "data": data}


# ============================================================
# 4) SENTIMENT BREAKDOWN (pos/neu/neg)
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
        raise HTTPException(404, "Company not found")

    q = db.query(Review).filter(Review.company_id == company_id)
    q = _apply_date_filter(q, start, end)

    # If sentiment_category is present, aggregate it; else infer from rating.
    pos = neu = neg = 0

    # Prefer DB aggregation by label
    if hasattr(Review, "sentiment_category"):
        rows: List[Tuple] = (
            q.with_entities(Review.sentiment_category, func.count(Review.id))
             .group_by(Review.sentiment_category)
             .all()
        )
        buckets = defaultdict(int)
        for cat, cnt in rows:
            c = (cat or "neutral").lower()
            if c.startswith("pos"):
                buckets["pos"] += cnt
            elif c.startswith("neg"):
                buckets["neg"] += cnt
            else:
                buckets["neu"] += cnt
        pos, neu, neg = buckets["pos"], buckets["neu"], buckets["neg"]
    else:
        # Fallback: 4-5 → pos, 3/None → neu, 1-2 → neg
        for r in q.with_entities(Review.rating).all():
            rv = r[0]
            if rv is None or rv == 3:
                neu += 1
            elif rv >= 4:
                pos += 1
            else:
                neg += 1

    return {"pos": int(pos), "neu": int(neu), "neg": int(neg)}


# ============================================================
# 5) REVENUE PREDICTION (simple, heuristic proxy)
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
        raise HTTPException(404, "Company not found")

    q = db.query(Review).filter(Review.company_id == company_id)
    q = _apply_date_filter(q, start, end)

    rows = q.with_entities(Review.review_date, Review.rating).all()
    monthly = defaultdict(lambda: {"count": 0, "sum_rating": 0.0})

    for dt, rating in rows:
        if not dt:
            continue
        key = dt.strftime("%Y-%m")
        monthly[key]["count"] += 1
        monthly[key]["sum_rating"] += float(rating or 0.0)

    months_sorted = sorted(monthly.keys())[-6:] if monthly else []
    labels: List[str] = []
    data: List[float] = []
    for key in months_sorted:
        ym = datetime.strptime(key, "%Y-%m")
        labels.append(ym.strftime("%b %Y"))
        cnt = monthly[key]["count"]
        avg = (monthly[key]["sum_rating"] / cnt) if cnt else 0.0
        data.append(round(max(0.0, cnt * (avg / 5.0) * 100.0), 2))

    if not labels:
        labels = ["Jan", "Feb", "Mar", "Apr", "May", "Jun"]
        data = [0, 0, 0, 0, 0, 0]

    return {"labels": labels, "data": data}


# ============================================================
# 6) SYNC REVIEWS (re-uses ingestion used by reviews.py)
# ============================================================
@router.post("/reviews/sync")
def sync_reviews(
    company_id: int = Query(..., alias="company_id"),
    db: Session = Depends(get_db),
    max_reviews: int = Query(60, ge=1, le=200),
):
    """
    Trigger a review sync for this company.
    Delegates to services.ingestion.fetch_and_save_reviews_places if available.
    """
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(404, "Company not found")

    try:
        from ..services.ingestion import fetch_and_save_reviews_places
    except Exception:
        # Keep this route non-failing; front-end can still use /google/import
        return {"ok": False, "message": "Ingestion service not available; use /api/reviews/google/import/{company_id}"}

    added = fetch_and_save_reviews_places(company, db, max_reviews=max_reviews)
    return {"ok": True, "added": int(added or 0)}


# ============================================================
# 7) SOURCES BREAKDOWN (UI expects this; we bucket as 'google')
# ============================================================
@router.get("/sources")
def get_sources_breakdown(
    company_id: int = Query(..., alias="company_id"),
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """
    Your Review model has no 'source' column. Since you're ingesting from Google
    Places, we expose one bucket 'google' with total count so the pie chart renders.
    """
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(404, "Company not found")

    q = db.query(Review).filter(Review.company_id == company_id)
    q = _apply_date_filter(q, start, end)

    total = q.count()
    labels = ["google"]
    data = [int(total)]
    return {"labels": labels, "data": data}


# ============================================================
# 8) HEATMAP (hour-of-day histogram 0..23)
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
        raise HTTPException(404, "Company not found")

    q = db.query(Review).filter(Review.company_id == company_id)
    q = _apply_date_filter(q, start, end)

    hours = [0] * 24
    for (dt,) in q.with_entities(Review.review_date).all():
        if isinstance(dt, datetime):
            hours[dt.hour] += 1

    return {"labels": list(range(24)), "data": hours}


# ============================================================
# 9) REVIEWS TABLE (paginated + search + sort)
# ============================================================
@router.get("/reviews")
def get_reviews_table(
    company_id: int = Query(..., alias="company_id"),
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(25, ge=1, le=200),
    search: Optional[str] = Query(None, min_length=1),
    sort: str = Query("review_date", regex=r"^(review_date|rating)$"),
    order: str = Query("desc", regex=r"^(asc|desc)$"),
    db: Session = Depends(get_db),
):
    """
    Returns paginated reviews shaped for dashboard table.
    - Search across Review.text and Review.reviewer_name.
    - Sort by review_date or rating only (both exist in the schema).
    """
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(404, "Company not found")

    q = db.query(Review).filter(Review.company_id == company_id)
    q = _apply_date_filter(q, start, end)

    if search:
        term = f"%{search.strip()}%"
        # Only fields that exist in your model
        q = q.filter(
            (Review.text.ilike(term)) |
            (Review.reviewer_name.ilike(term))
        )

    total = q.count()

    sort_col = getattr(Review, sort)
    q = q.order_by(sort_col.desc() if order == "desc" else sort_col.asc())

    rows: List[Review] = q.offset((page - 1) * limit).limit(limit).all()

    def to_dict(r: Review) -> Dict[str, Any]:
        return {
            "id": r.id,
            "review_date": r.review_date.isoformat() if r.review_date else None,
            "rating": float(r.rating or 0.0),
            "text": r.text,
            "reviewer_name": r.reviewer_name,
            "reviewer_avatar": r.reviewer_avatar,
            "sentiment_category": r.sentiment_category,
            "sentiment_score": r.sentiment_score,
            "keywords": r.keywords,
            "language": r.language,
            "external_id": r.external_id,
            "fetch_status": r.fetch_status,
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
# 10) KEYWORDS (top terms)
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
        raise HTTPException(404, "Company not found")

    q = db.query(Review).filter(Review.company_id == company_id)
    q = _apply_date_filter(q, start, end)

    buckets: Dict[str, int] = defaultdict(int)

    # Prefer structured keywords (comma/semicolon separated)
    for kw, in q.with_entities(Review.keywords).all():
        val = (kw or "").strip()
        if not val:
            continue
        parts = [p.strip().lower() for p in val.replace(";", ",").split(",") if p.strip()]
        for p in parts:
            buckets[p] += 1

    # Fallback: extract from text if keywords are often empty
    if not buckets:
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
# 11) ALERTS (rating drop/increase; volume spike)
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
        raise HTTPException(404, "Company not found")

    base_q = db.query(Review).filter(Review.company_id == company_id)
    base_q = _apply_date_filter(base_q, start, end)

    min_dt, max_dt = base_q.with_entities(
        func.min(Review.review_date), func.max(Review.review_date)
    ).first() or (None, None)

    if not min_dt or not max_dt:
        return {"alerts": []}

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
# 12) EXPORT (CSV) aligned to your Review schema
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
        raise HTTPException(404, "Company not found")

    q = db.query(Review).filter(Review.company_id == company_id)
    q = _apply_date_filter(q, start, end)
    q = q.order_by(Review.review_date.desc())

    buffer = io.StringIO()
    writer = csv.writer(buffer)

    # Header strictly matches your Review model fields
    header = [
        "id", "external_id", "review_date", "rating", "text",
        "reviewer_name", "reviewer_avatar", "language",
        "sentiment_category", "sentiment_score", "keywords", "fetch_status"
    ]
    writer.writerow(header)

    for r in q.all():
        writer.writerow([
            r.id,
            r.external_id or "",
            r.review_date.isoformat() if r.review_date else "",
            r.rating if r.rating is not None else "",
            r.text or "",
            r.reviewer_name or "",
            r.reviewer_avatar or "",
            r.language or "",
            r.sentiment_category or "",
            r.sentiment_score if r.sentiment_score is not None else "",
            r.keywords or "",
            r.fetch_status or "",
        ])

    buffer.seek(0)
    filename = f"reviews_company_{company_id}.csv"
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )
