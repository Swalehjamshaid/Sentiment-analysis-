# FILE: app/services/analysis.py
"""
Database-aware analysis helpers aligned to app/models.py structures
for use primarily by dashboard.html and related API endpoints.

All date filtering is inclusive on both ends where applicable.
All returned dictionaries are JSON-serializable.
"""

from __future__ import annotations

import math
from typing import Optional, Dict, Any, List, Tuple, Union
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

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
# Date & Filter Utilities
# ─────────────────────────────────────────────────────────────

def _parse_date(value: Optional[str]) -> Optional[datetime]:
    """
    Convert various date string formats into timezone-aware UTC datetime.
    Returns None on any parsing failure (lenient behavior).
    """
    if not value:
        return None

    value = value.strip()

    # 1. Try YYYY-MM-DD
    try:
        dt = datetime.strptime(value, "%Y-%m-%d")
        return dt.replace(tzinfo=timezone.utc)
    except ValueError:
        pass

    # 2. Try full ISO format (with or without timezone)
    try:
        dt = datetime.fromisoformat(value)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        pass

    return None


def _apply_date_filter(
    query,
    start: Optional[str] = None,
    end: Optional[str] = None
) -> Any:
    """
    Apply inclusive date range filter on Review.review_date.
    When end date has no time component, includes whole end day.
    """
    start_dt = _parse_date(start)
    end_dt   = _parse_date(end)

    if start_dt is not None:
        query = query.filter(Review.review_date >= start_dt)

    if end_dt is not None:
        if end_dt.hour == 0 and end_dt.minute == 0 and end_dt.second == 0:
            # Pure date → include whole day
            query = query.filter(Review.review_date < (end_dt + timedelta(days=1)))
        else:
            # Has time → strict ≤
            query = query.filter(Review.review_date <= end_dt)

    return query


def get_company_or_404(db: Session, company_id: int) -> Company:
    """Retrieve company or raise descriptive exception"""
    company = db.query(Company).filter(Company.id == company_id).first()
    if company is None:
        raise ValueError(f"Company with ID {company_id} not found")
    return company


def fetch_reviews(
    db: Session,
    company_id: int,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> List[Review]:
    """Centralized reviews fetch with date filtering"""
    q = db.query(Review).filter(Review.company_id == company_id)
    q = _apply_date_filter(q, start, end)
    return q.all()


# ─────────────────────────────────────────────────────────────
# Individual Dashboard Blocks
# ─────────────────────────────────────────────────────────────

def metrics_block(
    db: Session,
    company_id: int,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> Dict[str, Any]:
    reviews = fetch_reviews(db, company_id, start, end)
    return metrics_payload(reviews, _parse_date(start), _parse_date(end))


def trend_block(
    db: Session,
    company_id: int,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> Dict[str, Any]:
    reviews = fetch_reviews(db, company_id, start, end)
    return trend_timeseries(reviews, _parse_date(start), _parse_date(end))


def sentiment_block(
    db: Session,
    company_id: int,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> Dict[str, int]:
    reviews = fetch_reviews(db, company_id, start, end)
    return sentiment_buckets(reviews, _parse_date(start), _parse_date(end))


def sources_block(
    db: Session,
    company_id: int,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> Dict[str, Union[List[str], List[int]]]:
    """
    Aggregate review count by language (used as proxy for source/platform).
    Returns chart-ready format: {"labels": [...], "data": [...]}
    """
    q = db.query(
        Review.language,
        func.count(Review.id).label("cnt")
    ).filter(
        Review.company_id == company_id
    )

    q = _apply_date_filter(q, start, end)
    q = q.group_by(Review.language)

    rows = q.all()

    if not rows:
        total_q = db.query(func.count(Review.id)).filter(Review.company_id == company_id)
        total = _apply_date_filter(total_q, start, end).scalar() or 0
        return {"labels": ["unknown"], "data": [int(total)]}

    buckets: Dict[str, int] = {}
    for lang, count in rows:
        key = (lang or "unknown").strip() or "unknown"
        buckets[key] = int(count)

    labels = list(buckets.keys())
    data = [buckets[k] for k in labels]

    return {"labels": labels, "data": data}


def heatmap_block(
    db: Session,
    company_id: int,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> Dict[str, Any]:
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
    return detect_alerts(
        reviews,
        _parse_date(start),
        _parse_date(end),
        window_days=window_days
    )


def revenue_block(
    db: Session,
    company_id: int,
    start: Optional[str] = None,
    end: Optional[str] = None,
    months_back: int = 6,
) -> Dict[str, Any]:
    reviews = fetch_reviews(db, company_id, start, end)
    return revenue_proxy_monthly(
        reviews,
        _parse_date(start),
        _parse_date(end),
        months_back=months_back
    )


# ─────────────────────────────────────────────────────────────
# Paginated Reviews Table
# ─────────────────────────────────────────────────────────────

def _apply_search_filters(query, search: Optional[str]) -> Any:
    """Case-insensitive full-text-ish search across main review fields"""
    if not search or not (term := search.strip()):
        return query

    pattern = f"%{term}%"

    searchable = [
        "text",
        "reviewer_name",
        "keywords",
        "language",
        "sentiment_category",
    ]

    conditions = [
        getattr(Review, col).ilike(pattern)
        for col in searchable
        if hasattr(Review, col)
    ]

    return query.filter(or_(*conditions)) if conditions else query


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
    """
    Paginated, searchable, sortable list of reviews.
    Returns shape expected by most frontend tables.
    """
    q = db.query(Review).filter(Review.company_id == company_id)
    q = _apply_date_filter(q, start, end)
    q = _apply_search_filters(q, search)

    total = q.count()

    # ── Sorting ────────────────────────────────────────
    allowed_sort_fields = {"review_date", "rating", "sentiment_category", "fetch_at"}
    sort_field = sort if sort in allowed_sort_fields else "review_date"

    sort_column = getattr(Review, sort_field)
    q = q.order_by(
        sort_column.desc() if order.lower() == "desc" else sort_column.asc()
    )

    # ── Pagination ─────────────────────────────────────
    page  = max(1, int(page))
    limit = max(1, min(500, int(limit)))   # reasonable upper bound

    offset = (page - 1) * limit
    rows = q.offset(offset).limit(limit).all()

    # ── Serialization ──────────────────────────────────
    data = [{
        "id":               r.id,
        "review_date":      r.review_date.isoformat() if r.review_date else None,
        "rating":           int(r.rating or 0),
        "text":             r.text or "",
        "reviewer_name":    r.reviewer_name,
        "reviewer_avatar":  r.reviewer_avatar,
        "sentiment_category": r.sentiment_category,
        "sentiment_score":  float(r.sentiment_score or 0.0),
        "keywords":         r.keywords or [],
        "language":         r.language,
        "fetch_at":         r.fetch_at.isoformat() if r.fetch_at else None,
        "fetch_status":     r.fetch_status,
    } for r in rows]

    return {
        "page":   page,
        "limit":  limit,
        "total":  total,
        "pages":  math.ceil(total / limit) if limit > 0 else 1,
        "data":   data,
    }


# ─────────────────────────────────────────────────────────────
# Unified Dashboard Payload (most complete view)
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
    """
    Comprehensive payload containing almost everything needed
    to render a modern company review dashboard.
    """
    company = get_company_or_404(db, company_id)
    reviews = fetch_reviews(db, company_id, start, end)

    start_dt = _parse_date(start)
    end_dt   = _parse_date(end)

    # Core AI-powered analysis (most expensive part)
    core_analysis = analyze_reviews(
        reviews,
        company,
        start_dt,
        end_dt,
        include_aspects=True
    )

    return {
        "company": {
            "id": company.id,
            "name": company.name,
            "city": company.city,
            "status": company.status,
        },

        # Basic KPIs
        "metrics": {
            "total":        core_analysis.get("total_reviews", 0),
            "avg_rating":   core_analysis.get("avg_rating", 0.0),
            "risk_score":   core_analysis.get("risk_score", 0.0),
            "risk_level":   core_analysis.get("risk_level", "Low"),
        },

        # Trend visualization
        "trend": {
            "labels": [x["month"] for x in core_analysis.get("trend_data", [])],
            "data":   [x["avg_rating"] for x in core_analysis.get("trend_data", [])],
            "signal": core_analysis.get("trend", {}).get("signal"),
            "delta":  core_analysis.get("trend", {}).get("delta"),
        },

        "sentiment":        core_analysis.get("sentiments", {}),
        "daily_series":     core_analysis.get("daily_series", []),
        "aspects":          core_analysis.get("aspects", []),
        "ai_recommendations": core_analysis.get("ai_recommendations", []),

        # Additional specialized blocks
        "sources":  sources_block(db, company_id, start, end),
        "heatmap":  hour_heatmap(reviews, start_dt, end_dt),
        "keywords": top_keywords(reviews, start_dt, end_dt, top_n=top_keywords_n),
        "alerts":   detect_alerts(reviews, start_dt, end_dt, window_days=alerts_window_days).get("alerts", []),
        "revenue":  revenue_proxy_monthly(reviews, start_dt, end_dt, months_back=revenue_months_back),

        # Metadata
        "window":   core_analysis.get("window", {}),
        "version":  "3.5",
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
