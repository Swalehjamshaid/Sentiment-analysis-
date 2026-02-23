# FILE: app/services/analysis.py
"""
Database-aware analysis helpers for dashboard.html.

Bridges the ORM in `app/models.py` (Company, Review) with the
pure-Python analytics in `app/services/ai_insights.py`.

✔ Aligns with your actual schema from models.py:
   - Review fields used: text, rating, review_date, reviewer_name,
     reviewer_avatar, sentiment_category, sentiment_score, keywords,
     language, fetch_at, fetch_status, external_id
   - Company fields used: id, name, city, status

Provided capabilities:
- Fetch filtered reviews by company/date range
- Metrics/trend/sentiment/heatmap/keywords/alerts/revenue blocks
- Server-side paginated reviews table
- Unified dashboard payload for one-shot hydration

Notes:
- We do NOT mutate the DB here (read-only analytics).
- We defensively check attributes with hasattr/getattr to tolerate
  optional columns and keep the module resilient.
- For "sources" breakdown, since the schema has no `source` column,
  the underlying helper returns a single bucket "unknown" (graceful fallback).
"""
from __future__ import annotations

from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

try:
    from ..models import Company, Review
    from .ai_insights import (
        metrics_payload,
        trend_timeseries,
        sentiment_buckets,
        sources_breakdown,      # will gracefully fallback to "unknown" bucket
        hour_heatmap,
        top_keywords,
        detect_alerts,
        revenue_proxy_monthly,
        analyze_reviews,
    )
except Exception as _imp_err:  # pragma: no cover
    Company = object  # type: ignore
    Review = object  # type: ignore
    def _missing(*args, **kwargs):  # type: ignore
        raise RuntimeError("Required modules not available: " + str(_imp_err))
    metrics_payload = trend_timeseries = sentiment_buckets = sources_breakdown = _missing  # type: ignore
    hour_heatmap = top_keywords = detect_alerts = revenue_proxy_monthly = analyze_reviews = _missing  # type: ignore


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def _parse_date(s: Optional[str]) -> Optional[datetime]:
    """Parse 'YYYY-MM-DD' or ISO datetime string into datetime.
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
    If only date (no time) is given for end, include the full end day.
    """
    start_dt = _parse_date(start)
    end_dt = _parse_date(end)
    if start_dt is not None:
        query = query.filter(Review.review_date >= start_dt)
    if end_dt is not None:
        # full end-of-day if time was not provided
        if end_dt.hour == 0 and end_dt.minute == 0 and end_dt.second == 0 and end_dt.microsecond == 0:
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
):
    """Return Review rows for a company with optional date filters."""
    q = db.query(Review).filter(Review.company_id == company_id)
    q = _apply_date_filter(q, start, end)
    return q.all()


# ─────────────────────────────────────────────────────────────
# Dashboard widget blocks (DB-backed → pure helpers)
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
    reviews = fetch_reviews(db, company_id, start, end)
    return sources_breakdown(reviews, _parse_date(start), _parse_date(end))


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
# Data table utilities (server-side pagination)
# ─────────────────────────────────────────────────────────────

def _apply_search_filters(q, search: Optional[str]):
    """Apply case-insensitive LIKE filters over common Review columns."""
    if not search:
        return q
    s = f"%{search.strip()}%"
    from sqlalchemy import or_
    filters = []
    # Match your schema: text, reviewer_name, keywords, language
    for col in ("text", "reviewer_name", "keywords", "language"):
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
    """Return paginated reviews with fields aligned to models.py for tables."""
    q = db.query(Review).filter(Review.company_id == company_id)
    q = _apply_date_filter(q, start, end)
    q = _apply_search_filters(q, search)

    total = q.count()

    # Sorting: support safe columns from your schema
    preferred_order = [
        "review_date", "rating", "sentiment_score", "fetch_at", "language",
    ]
    valid_sort = sort if hasattr(Review, sort) else next((c for c in preferred_order if hasattr(Review, c)), "review_date")
    sort_col = getattr(Review, valid_sort)
    q = q.order_by(sort_col.desc() if order == "desc" else sort_col.asc())

    # Pagination
    page = max(1, int(page))
    limit = max(1, min(500, int(limit)))
    offset = (page - 1) * limit

    rows = q.offset(offset).limit(limit).all()

    def to_dict(r) -> Dict[str, Any]:
        return {
            "id": getattr(r, "id", None),
            "external_id": getattr(r, "external_id", None) if hasattr(r, "external_id") else None,
            "review_date": getattr(r, "review_date", None).isoformat() if getattr(r, "review_date", None) else None,
            "rating": int(getattr(r, "rating", 0) or 0),
            "text": getattr(r, "text", None),
            "reviewer_name": getattr(r, "reviewer_name", None) if hasattr(r, "reviewer_name") else None,
            "reviewer_avatar": getattr(r, "reviewer_avatar", None) if hasattr(r, "reviewer_avatar") else None,
            "sentiment_category": getattr(r, "sentiment_category", None) if hasattr(r, "sentiment_category") else None,
            "sentiment_score": float(getattr(r, "sentiment_score", 0.0) or 0.0) if hasattr(r, "sentiment_score") else None,
            "keywords": getattr(r, "keywords", None) if hasattr(r, "keywords") else None,
            "language": getattr(r, "language", None) if hasattr(r, "language") else None,
            "fetch_at": getattr(r, "fetch_at", None).isoformat() if hasattr(r, "fetch_at") and getattr(r, "fetch_at", None) else None,
            "fetch_status": getattr(r, "fetch_status", None) if hasattr(r, "fetch_status") else None,
        }

    data = [to_dict(r) for r in rows]

    from math import ceil
    return {
        "page": page,
        "limit": limit,
        "total": total,
        "pages": ceil(total / limit) if limit else 1,
        "data": data,
    }


# ─────────────────────────────────────────────────────────────
# Unified payload (single call from route for dashboard.html)
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
    """Build a comprehensive dashboard payload for a company/date window."""
    company = get_company_or_404(db, company_id)
    reviews = fetch_reviews(db, company_id, start, end)

    # Core insights (consistent, single source of truth)
    core = analyze_reviews(reviews, company, _parse_date(start), _parse_date(end), include_aspects=True)

    # Additional blocks commonly rendered on dashboard
    sources = sources_breakdown(reviews, _parse_date(start), _parse_date(end))  # will be {labels:["unknown"], data:[N]} if none
    heatmap = hour_heatmap(reviews, _parse_date(start), _parse_date(end))
    keywords = top_keywords(reviews, _parse_date(start), _parse_date(end), top_n=top_keywords_n)
    alerts = detect_alerts(reviews, _parse_date(start), _parse_date(end), window_days=alerts_window_days)
    revenue = revenue_proxy_monthly(reviews, _parse_date(start), _parse_date(end), months_back=revenue_months_back)

    return {
        "company": {
            "id": getattr(company, "id", None),
            "name": getattr(company, "name", None),
            "city": getattr(company, "city", None) if hasattr(company, "city") else None,
            "status": getattr(company, "status", None) if hasattr(company, "status") else None,
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
