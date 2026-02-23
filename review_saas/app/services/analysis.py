# FILE: app/services/analysis.py
"""
Database-aware analysis helpers aligned to app/models.py for dashboard.html.
"""
from __future__ import annotations

from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta, timezone
from math import ceil

from sqlalchemy.orm import Session
from sqlalchemy import func, or_

from ..models import Company, Review
from .ai_insights import (
    metrics_payload,
    trend_timeseries,
    sentiment_buckets,
    hour_heatmap,
    top_keywords,
    detect_alerts,
    revenue_proxy_monthly,
    analyze_reviews,
)

# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def _parse_date(s: Optional[str]) -> Optional[datetime]:
    """Parse 'YYYY-MM-DD' or ISO datetime string into a UTC datetime."""
    if not s:
        return None
    try:
        dt = datetime.strptime(s, "%Y-%m-%d")
        return dt.replace(tzinfo=timezone.utc)
    except Exception:
        try:
            dt = datetime.fromisoformat(s)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except Exception:
            return None


def _apply_date_filter(query, start: Optional[str], end: Optional[str]):
    """Apply inclusive date range filters on Review.review_date."""
    start_dt = _parse_date(start)
    end_dt = _parse_date(end)
    if start_dt:
        query = query.filter(Review.review_date >= start_dt)
    if end_dt:
        # If end_dt is a pure date (00:00:00), include the entire day up to 23:59:59
        if end_dt.hour == 0 and end_dt.minute == 0 and end_dt.second == 0:
            query = query.filter(Review.review_date < (end_dt + timedelta(days=1)))
        else:
            query = query.filter(Review.review_date <= end_dt)
    return query


def get_company_or_404(db: Session, company_id: int) -> Company:
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise ValueError(f"Company ID {company_id} not found")
    return company


def fetch_reviews(
    db: Session,
    company_id: int,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> List[Review]:
    q = db.query(Review).filter(Review.company_id == company_id)
    q = _apply_date_filter(q, start, end)
    return q.all()


# ─────────────────────────────────────────────────────────────
# Dashboard Blocks
# ─────────────────────────────────────────────────────────────

def metrics_block(db: Session, company_id: int, start: Optional[str] = None, end: Optional[str] = None) -> Dict[str, Any]:
    reviews = fetch_reviews(db, company_id, start, end)
    return metrics_payload(reviews, _parse_date(start), _parse_date(end))


def trend_block(db: Session, company_id: int, start: Optional[str] = None, end: Optional[str] = None) -> Dict[str, Any]:
    reviews = fetch_reviews(db, company_id, start, end)
    return trend_timeseries(reviews, _parse_date(start), _parse_date(end))


def sentiment_block(db: Session, company_id: int, start: Optional[str] = None, end: Optional[str] = None) -> Dict[str, int]:
    reviews = fetch_reviews(db, company_id, start, end)
    return sentiment_buckets(reviews, _parse_date(start), _parse_date(end))


def sources_block(db: Session, company_id: int, start: Optional[str] = None, end: Optional[str] = None) -> Dict[str, Any]:
    """Aggregate by language as a proxy for source."""
    q = db.query(Review.language, func.count(Review.id)).filter(Review.company_id == company_id)
    q = _apply_date_filter(q, start, end)
    q = q.group_by(Review.language)
    rows = q.all()

    buckets: Dict[str, int] = {}
    for lang, cnt in rows:
        key = (lang or "unknown").strip() or "unknown"
        buckets[key] = int(cnt)

    if not buckets:
        total_q = db.query(func.count(Review.id)).filter(Review.company_id == company_id)
        total = _apply_date_filter(total_q, start, end).scalar() or 0
        return {"labels": ["unknown"], "data": [int(total)]}

    labels = list(buckets.keys())
    data = [buckets[k] for k in labels]
    return {"labels": labels, "data": data}


def heatmap_block(db: Session, company_id: int, start: Optional[str] = None, end: Optional[str] = None) -> Dict[str, Any]:
    reviews = fetch_reviews(db, company_id, start, end)
    return hour_heatmap(reviews, _parse_date(start), _parse_date(end))


def keywords_block(db: Session, company_id: int, start: Optional[str] = None, end: Optional[str] = None, top_n: int = 20) -> Dict[str, Any]:
    reviews = fetch_reviews(db, company_id, start, end)
    return top_keywords(reviews, _parse_date(start), _parse_date(end), top_n=top_n)


def alerts_block(db: Session, company_id: int, start: Optional[str] = None, end: Optional[str] = None, window_days: int = 14) -> Dict[str, Any]:
    reviews = fetch_reviews(db, company_id, start, end)
    return detect_alerts(reviews, _parse_date(start), _parse_date(end), window_days=window_days)


def revenue_block(db: Session, company_id: int, start: Optional[str] = None, end: Optional[str] = None, months_back: int = 6) -> Dict[str, Any]:
    reviews = fetch_reviews(db, company_id, start, end)
    return revenue_proxy_monthly(reviews, _parse_date(start), _parse_date(end), months_back=months_back)


# ─────────────────────────────────────────────────────────────
# Reviews Table Logic
# ─────────────────────────────────────────────────────────────

def _apply_search_filters(q, search: Optional[str]):
    if not search:
        return q
    s = f"%{search.strip()}%"
    # Filterable columns based on model availability
    cols_to_search = ["text", "reviewer_name", "keywords", "language", "sentiment_category"]
    filters = [getattr(Review, col).ilike(s) for col in cols_to_search if hasattr(Review, col)]
    return q.filter(or_(*filters)) if filters else q


def reviews_table(
    db: Session,
    company_id: int,
    page: int = 1,
    limit: int = 25,
    search: Optional[str] = None,
    sort: str = "review_date",
    order: str = "desc",
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> Dict[str, Any]:
    q = db.query(Review).filter(Review.company_id == company_id)
    q = _apply_date_filter(q, start, end)
    q = _apply_search_filters(q, search)

    total = q.count()

    allowed_sorts = {"review_date", "rating", "sentiment_category", "fetch_at"}
    sort_key = sort if sort in allowed_sorts else "review_date"
    sort_col = getattr(Review, sort_key)
    q = q.order_by(sort_col.desc() if order == "desc" else sort_col.asc())

    page = max(1, int(page))
    limit = max(1, min(500, int(limit)))
    rows = q.offset((page - 1) * limit).limit(limit).all()

    data = [{
        "id": r.id,
        "review_date": r.review_date.isoformat() if r.review_date else None,
        "rating": int(r.rating or 0),
        "text": r.text,
        "reviewer_name": r.reviewer_name,
        "reviewer_avatar": r.reviewer_avatar,
        "sentiment_category": r.sentiment_category,
        "sentiment_score": float(r.sentiment_score or 0.0),
        "keywords": r.keywords,
        "language": r.language,
        "fetch_at": r.fetch_at.isoformat() if r.fetch_at else None,
        "fetch_status": r.fetch_status,
    } for r in rows]

    return {
        "page": page,
        "limit": limit,
        "total": total,
        "pages": ceil(total / limit) if limit > 0 else 1,
        "data": data,
    }


# ─────────────────────────────────────────────────────────────
# Unified Payload
# ─────────────────────────────────────────────────────────────

def dashboard_payload(
    db: Session,
    company_id: int,
    start: Optional[str] = None,
    end: Optional[str] = None,
    top_keywords_n: int = 20,
    alerts_window_days: int = 14,
    revenue_months_back: int = 6,
) -> Dict[str, Any]:
    company = get_company_or_404(db, company_id)
    reviews = fetch_reviews(db, company_id, start, end)

    start_dt, end_dt = _parse_date(start), _parse_date(end)
    core = analyze_reviews(reviews, company, start_dt, end_dt, include_aspects=True)

    return {
        "company": {
            "id": company.id,
            "name": company.name,
            "city": company.city,
            "status": company.status,
        },
        "metrics": {
            "total": core.get("total_reviews", 0),
            "avg_rating": core.get("avg_rating", 0.0),
            "risk_score": core.get("risk_score", 0.0),
            "risk_level": core.get("risk_level", "Low"),
        },
        "trend": {
            "labels": [x["month"] for x in core.get("trend_data", [])],
            "data": [x["avg_rating"] for x in core.get("trend_data", [])],
            "signal": core.get("trend", {}).get("signal"),
            "delta": core.get("trend", {}).get("delta"),
        },
        "sentiment": core.get("sentiments", {}),
        "daily_series": core.get("daily_series", []),
        "aspects": core.get("aspects", []),
        "ai_recommendations": core.get("ai_recommendations", []),
        "sources": sources_block(db, company_id, start, end),
        "heatmap": hour_heatmap(reviews, start_dt, end_dt),
        "keywords": top_keywords(reviews, start_dt, end_dt, top_n=top_keywords_n),
        "alerts": detect_alerts(reviews, start_dt, end_dt, window_days=alerts_window_days).get("alerts", []),
        "revenue": revenue_proxy_monthly(reviews, start_dt, end_dt, months_back=revenue_months_back),
        "window": core.get("window", {}),
        "version": "3.5",
    }


__all__ = [
    "get_company_or_404",
    "fetch_reviews",
    "metrics_block",
    "trend_block",
    "sentiment_block",
    "sources_block",
    "heatmap_block",
    "keywords_block",
    "alerts_block",
    "revenue_block",
    "reviews_table",
    "dashboard_payload",
]
