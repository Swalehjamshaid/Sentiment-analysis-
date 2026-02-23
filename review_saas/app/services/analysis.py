# FILE: app/services/analysis.py
"""
Database-aware analysis helpers aligned to app/models.py for dashboard.html.

This module bridges SQLAlchemy ORM models (Company, Review) with
pure-Python analytics in `app/services/ai_insights.py` and returns
ready-to-serialize payloads for the dashboard.

Key capabilities
----------------
- Date parsing and inclusive date filtering (by review_date)
- Safe, defensive access to optional Review fields (keywords, language, etc.)
- Metrics/trend/sentiment/keywords/alerts/revenue blocks
- Server-side reviews table (search/sort/pagination)
- Unified dashboard payload (single call)

Note: The `Review` model (see app/models.py) includes: text, rating, review_date,
reviewer_name, reviewer_avatar, sentiment_category, sentiment_score, keywords,
language, fetch_at, fetch_status. There is no `source`, `title`, or `url`.
This module avoids referencing non-existent fields and adds sensible fallbacks.
"""
from __future__ import annotations

from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from math import ceil

from sqlalchemy.orm import Session
from sqlalchemy import func

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
    """Parse 'YYYY-MM-DD' or ISO datetime string into a datetime.
    Returns None on failure.
    """
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
    """Apply inclusive date range filters on Review.review_date.
    If only date (no time) is provided for end, include the entire end day.
    """
    start_dt = _parse_date(start)
    end_dt = _parse_date(end)
    if start_dt is not None:
        query = query.filter(Review.review_date >= start_dt)
    if end_dt is not None:
        if end_dt.hour == 0 and end_dt.minute == 0 and end_dt.second == 0:
            query = query.filter(Review.review_date < (end_dt + timedelta(days=1)))
        else:
            query = query.filter(Review.review_date <= end_dt)
    return query


def get_company_or_404(db: Session, company_id: int) -> Company:
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise ValueError("Company not found")
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
# Blocks (DB-backed → pure helpers)
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
    """Aggregate by a best-effort 'source' proxy.
    Since the Review model has no explicit source, we fallback to `language`.
    If language is missing, return a single "unknown" bucket.
    """
    q = db.query(Review.language, func.count(Review.id)).filter(Review.company_id == company_id)
    q = _apply_date_filter(q, start, end)
    q = q.group_by(Review.language)
    rows = q.all()

    # Build buckets
    buckets: Dict[str, int] = {}
    total = 0
    for lang, cnt in rows:
        key = (lang or "unknown").strip() or "unknown"
        buckets[key] = int(cnt)
        total += int(cnt)

    # Fallback if no rows
    if not buckets:
        # count total in date range
        total = db.query(func.count(Review.id)).filter(Review.company_id == company_id)
        total = _apply_date_filter(total, start, end).scalar() or 0
        return {"labels": ["unknown"], "data": [int(total)]}

    labels = list(buckets.keys())
    data = [buckets[k] for k in labels]
    return {"labels": labels, "data": data}


def heatmap_block(db: Session, company_id: int, start: Optional[str] = None, end: Optional[str] = None) -> Dict[str, Any]:
    reviews = fetch_reviews(db, company_id, start, end)
    return hour_heatmap(reviews, _parse_date(start), _parse_date(end))


def keywords_block(
    db: Session,
    company_id: int,
    start: Optional[str] = None,
    end: Optional[str] = None,
    top_n: int = 20,
) -> Dict[str, Any]:
    reviews = fetch_reviews(db, company_id, start, end)
    return top_keywords(reviews, _parse_date(start), _parse_date(end), top_n=top_n)


def alerts_block(
    db: Session,
    company_id: int,
    start: Optional[str] = None,
    end: Optional[str] = None,
    window_days: int = 14,
) -> Dict[str, Any]:
    reviews = fetch_reviews(db, company_id, start, end)
    return detect_alerts(reviews, _parse_date(start), _parse_date(end), window_days=window_days)


def revenue_block(
    db: Session,
    company_id: int,
    start: Optional[str] = None,
    end: Optional[str] = None,
    months_back: int = 6,
) -> Dict[str, Any]:
    reviews = fetch_reviews(db, company_id, start, end)
    return revenue_proxy_monthly(reviews, _parse_date(start), _parse_date(end), months_back=months_back)


# ─────────────────────────────────────────────────────────────
# Reviews table (server-side pagination)
# ─────────────────────────────────────────────────────────────

def _apply_search_filters(q, search: Optional[str]):
    if not search:
        return q
    s = f"%{search.strip()}%"
    from sqlalchemy import or_
    filters = []
    # Available columns in Review per models.py
    for col in ("text", "reviewer_name", "keywords", "language", "sentiment_category", "fetch_status"):
        if hasattr(Review, col):
            filters.append(getattr(Review, col).ilike(s))
    if filters:
        q = q.filter(or_(*filters))
    return q


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

    # Sorting (allowed: review_date, rating, sentiment_category, fetch_at)
    allowed = {"review_date", "rating", "sentiment_category", "fetch_at"}
    sort_key = sort if sort in allowed else "review_date"
    sort_col = getattr(Review, sort_key)
    q = q.order_by(sort_col.desc() if order == "desc" else sort_col.asc())

    # Pagination
    page = max(1, int(page))
    limit = max(1, min(500, int(limit)))
    offset = (page - 1) * limit

    rows: List[Review] = q.offset(offset).limit(limit).all()

    def to_dict(r: Review) -> Dict[str, Any]:
        return {
            "id": getattr(r, "id", None),
            "review_date": (getattr(r, "review_date", None).isoformat() if getattr(r, "review_date", None) else None),
            "rating": int(getattr(r, "rating", 0) or 0),
            "text": getattr(r, "text", None),
            "reviewer_name": getattr(r, "reviewer_name", None),
            "reviewer_avatar": getattr(r, "reviewer_avatar", None),
            "sentiment_category": getattr(r, "sentiment_category", None),
            "sentiment_score": float(getattr(r, "sentiment_score", 0.0) or 0.0),
            "keywords": getattr(r, "keywords", None),
            "language": getattr(r, "language", None),
            "fetch_at": (getattr(r, "fetch_at", None).isoformat() if getattr(r, "fetch_at", None) else None),
            "fetch_status": getattr(r, "fetch_status", None),
        }

    data = [to_dict(r) for r in rows]

    return {
        "page": page,
        "limit": limit,
        "total": total,
        "pages": ceil(total / limit) if limit else 1,
        "data": data,
    }


# ─────────────────────────────────────────────────────────────
# Unified dashboard payload
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

    # core insights from AI module (includes trend, sentiments, risk, aspects, daily series)
    core = analyze_reviews(reviews, company, _parse_date(start), _parse_date(end), include_aspects=True)

    # extra widgets
    heatmap = hour_heatmap(reviews, _parse_date(start), _parse_date(end))
    keywords = top_keywords(reviews, _parse_date(start), _parse_date(end), top_n=top_keywords_n)
    alerts = detect_alerts(reviews, _parse_date(start), _parse_date(end), window_days=alerts_window_days)
    revenue = revenue_proxy_monthly(reviews, _parse_date(start), _parse_date(end), months_back=revenue_months_back)

    # best-effort proxy for sources by language
    sources = sources_block(db, company_id, start, end)

    return {
        "company": {
            "id": getattr(company, "id", None),
            "name": getattr(company, "name", None),
            "city": getattr(company, "city", None),
            "status": getattr(company, "status", None),
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
        "sources": sources,
        "heatmap": heatmap,
        "keywords": keywords,
        "alerts": alerts.get("alerts", []),
        "revenue": revenue,
        "window": core.get("window", {}),
        "version": core.get("payload_version", "3.3"),
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
