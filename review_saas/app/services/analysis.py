# FILE: app/services/analysis.py
"""
Database-aware analysis helpers aligned to app/models.py structures
for use primarily by dashboard.html and related API endpoints.

All date filtering is inclusive on both ends where applicable.
All returned dictionaries are JSON-serializable.

UPGRADE ADDITIONS (2026-02-24):
- 30-Day Insights Block (total, pos, neg, AI summary)
- Executive-level summary from existing analyze_reviews()
- Chart-ready daily trend + sentiment ring
- In-memory TTL caching (no existing code changed)
"""

from __future__ import annotations

import math
from typing import Optional, Dict, Any, List, Tuple, Union
from datetime import datetime, timedelta, timezone
from collections import defaultdict
import threading, os

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
# Date & Filter Utilities (unchanged from your file)
# ─────────────────────────────────────────────────────────────

def _parse_date(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    value = value.strip()
    try:
        dt = datetime.strptime(value, "%Y-%m-%d")
        return dt.replace(tzinfo=timezone.utc)
    except ValueError:
        pass
    try:
        dt = datetime.fromisoformat(value)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        pass
    return None


def _apply_date_filter(query, start: Optional[str] = None, end: Optional[str] = None):
    start_dt = _parse_date(start)
    end_dt   = _parse_date(end)

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
    if company is None:
        raise ValueError(f"Company with ID {company_id} not found")
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
# Existing Dashboard Blocks (UNCHANGED)
# ─────────────────────────────────────────────────────────────

def metrics_block(db, company_id, start=None, end=None):
    reviews = fetch_reviews(db, company_id, start, end)
    return metrics_payload(reviews, _parse_date(start), _parse_date(end))

def trend_block(db, company_id, start=None, end=None):
    reviews = fetch_reviews(db, company_id, start, end)
    return trend_timeseries(reviews, _parse_date(start), _parse_date(end))

def sentiment_block(db, company_id, start=None, end=None):
    reviews = fetch_reviews(db, company_id, start, end)
    return sentiment_buckets(reviews, _parse_date(start), _parse_date(end))

def sources_block(db, company_id, start=None, end=None):
    q = db.query(Review.language, func.count(Review.id).label("cnt"))
    q = q.filter(Review.company_id == company_id)
    q = _apply_date_filter(q, start, end)
    q = q.group_by(Review.language)

    rows = q.all()
    if not rows:
        total_q = db.query(func.count(Review.id)).filter(Review.company_id == company_id)
        total = _apply_date_filter(total_q, start, end).scalar() or 0
        return {"labels": ["unknown"], "data": [int(total)]}

    buckets = {}
    for lang, count in rows:
        key = (lang or "unknown").strip() or "unknown"
        buckets[key] = int(count)

    labels = list(buckets.keys())
    data = [buckets[k] for k in labels]
    return {"labels": labels, "data": data}

def heatmap_block(db, company_id, start=None, end=None):
    reviews = fetch_reviews(db, company_id, start, end)
    return hour_heatmap(reviews, _parse_date(start), _parse_date(end))

def keywords_block(db, company_id, start=None, end=None, top_n=20):
    reviews = fetch_reviews(db, company_id, start, end)
    return top_keywords(reviews, _parse_date(start), _parse_date(end), top_n=top_n)

def alerts_block(db, company_id, start=None, end=None, window_days=14):
    reviews = fetch_reviews(db, company_id, start, end)
    return detect_alerts(
        reviews,
        _parse_date(start),
        _parse_date(end),
        window_days=window_days,
    )

def revenue_block(db, company_id, start=None, end=None, months_back=6):
    reviews = fetch_reviews(db, company_id, start, end)
    return revenue_proxy_monthly(
        reviews,
        _parse_date(start),
        _parse_date(end),
        months_back=months_back,
    )

# ─────────────────────────────────────────────────────────────
# Reviews Table (unchanged)
# ─────────────────────────────────────────────────────────────

def _apply_search_filters(query, search):
    if not search or not (term := search.strip()):
        return query
    pattern = f"%{term}%"
    searchable = ["text", "reviewer_name", "keywords", "language", "sentiment_category"]
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
    q = db.query(Review).filter(Review.company_id == company_id)
    q = _apply_date_filter(q, start, end)
    q = _apply_search_filters(q, search)

    total = q.count()

    allowed_sort_fields = {"review_date", "rating", "sentiment_category", "fetch_at"}
    sort_field = sort if sort in allowed_sort_fields else "review_date"
    q = q.order_by(
        getattr(Review, sort_field).desc()
        if order.lower() == "desc"
        else getattr(Review, sort_field).asc()
    )

    page = max(1, int(page))
    limit = max(1, min(500, int(limit)))
    offset = (page - 1) * limit
    rows = q.offset(offset).limit(limit).all()

    data = [{
        "id": r.id,
        "review_date": r.review_date.isoformat() if r.review_date else None,
        "rating": int(r.rating or 0),
        "text": r.text or "",
        "reviewer_name": r.reviewer_name,
        "reviewer_avatar": r.reviewer_avatar,
        "sentiment_category": r.sentiment_category,
        "sentiment_score": float(r.sentiment_score or 0.0),
        "keywords": r.keywords or [],
        "language": r.language,
        "fetch_at": r.fetch_at.isoformat() if r.fetch_at else None,
        "fetch_status": r.fetch_status,
    } for r in rows]

    return {
        "page": page,
        "limit": limit,
        "total": total,
        "pages": math.ceil(total / limit) if limit > 0 else 1,
        "data": data,
    }

# ─────────────────────────────────────────────────────────────
# NEW: 30-DAY INSIGHTS ENGINE (ADD-ONLY)
# ─────────────────────────────────────────────────────────────

_LAST30D_CACHE = {}
_LAST30D_LOCK = threading.Lock()
_LAST30D_TTL_SECONDS = int(os.getenv("LAST30D_TTL_SECONDS", "300"))  # 5 min default


def _last30d_window():
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=30)
    return start, end


def _daily_counts_chart(reviews: List[Review]):
    by_date = defaultdict(lambda: {"total": 0, "positive": 0, "negative": 0})
    for r in reviews:
        if r.review_date:
            key = r.review_date.date().isoformat()
            by_date[key]["total"] += 1
            if r.sentiment_category == "positive":
                by_date[key]["positive"] += 1
            elif r.sentiment_category == "negative":
                by_date[key]["negative"] += 1

    start, end = _last30d_window()
    labels, totals, positives, negatives = [], [], [], []

    day = start.date()
    while day <= end.date():
        key = day.isoformat()
        labels.append(key)
        bucket = by_date.get(key, {"total": 0, "positive": 0, "negative": 0})
        totals.append(bucket["total"])
        positives.append(bucket["positive"])
        negatives.append(bucket["negative"])
        day += timedelta(days=1)

    return {
        "labels": labels,
        "datasets": {
            "total": totals,
            "positive": positives,
            "negative": negatives,
        }
    }


def _sentiment_ring(total: int, pos: int, neg: int):
    neutral = max(total - pos - neg, 0)
    return {
        "labels": ["Positive", "Negative", "Neutral"],
        "data": [pos, neg, neutral],
    }


def _exec_summary(analysis: Dict[str, Any]) -> Dict[str, Any]:
    avg_rating = analysis.get("avg_rating")
    total = analysis.get("total_reviews", 0)
    trend = analysis.get("trend", {})
    signal = (trend.get("signal") or "").lower()
    delta = trend.get("delta")

    phrase = {"up": "improving", "down": "declining", "flat": "stable"}.get(signal, "steady")
    delta_str = f" ({delta:+.2f} MoM)" if isinstance(delta, (float, int)) else ""

    snapshot = (
        f"Last 30 days captured {total} review(s). Average rating is {avg_rating:.2f}, sentiment is {phrase}{delta_str}."
        if avg_rating is not None else
        f"Last 30 days captured {total} review(s). Sentiment is {phrase}{delta_str}."
    )

    aspects = analysis.get("aspects", [])
    pos = [a for a in aspects if a.get("polarity") == "positive"][:3]
    neg = [a for a in aspects if a.get("polarity") == "negative"][:3]

    patterns = [f"{a['topic']}: {a.get('summary')}" for a in (pos[:2] + neg[:1])]
    risks = [f"{a['topic']} - negative trend" for a in neg]
    opportunities = [f"{a['topic']} - positive trend" for a in pos]

    recs = analysis.get("ai_recommendations", [])[:5]

    return {
        "executive_snapshot": snapshot,
        "patterns": patterns,
        "risks": risks,
        "opportunities": opportunities,
        "recommendations": recs,
    }


def last_30_days_block(db: Session, company_id: int) -> Dict[str, Any]:
    start, end = _last30d_window()
    cache_key = (company_id, start.date().isoformat(), end.date().isoformat())

    # Cache handling
    with _LAST30D_LOCK:
        cached = _LAST30D_CACHE.get(cache_key)
        if cached and cached["expires"] > datetime.now(timezone.utc).timestamp():
            return cached["data"]

    reviews = fetch_reviews(db, company_id, start.isoformat(), end.isoformat())
    total = len(reviews)
    pos = sum(1 for r in reviews if r.sentiment_category == "positive")
    neg = sum(1 for r in reviews if r.sentiment_category == "negative")

    company = get_company_or_404(db, company_id)

    analysis = analyze_reviews(
        reviews,
        company,
        start,
        end,
        include_aspects=True
    )

    payload = {
        "total_comments_30d": total,
        "positive_comments_30d": pos,
        "negative_comments_30d": neg,
        "ai_summary_30d": analysis.get("ai_recommendations", []),
        "executive_summary_30d": _exec_summary(analysis),
        "daily_counts": _daily_counts_chart(reviews),
        "sentiment_ring": _sentiment_ring(total, pos, neg),
        "window": {
            "start": start.isoformat(),
            "end": end.isoformat()
        },
        "cache": {
            "ttl_seconds": _LAST30D_TTL_SECONDS,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
    }

    with _LAST30D_LOCK:
        _LAST30D_CACHE[cache_key] = {
            "data": payload,
            "expires": datetime.now(timezone.utc).timestamp() + _LAST30D_TTL_SECONDS
        }

    return payload

# ─────────────────────────────────────────────────────────────
# Unified Dashboard Payload (UNCHANGED)
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

    start_dt = _parse_date(start)
    end_dt   = _parse_date(end)

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

        "metrics": {
            "total":        core_analysis.get("total_reviews", 0),
            "avg_rating":   core_analysis.get("avg_rating", 0.0),
            "risk_score":   core_analysis.get("risk_score", 0.0),
            "risk_level":   core_analysis.get("risk_level", "Low"),
        },

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

        "sources":  sources_block(db, company_id, start, end),
        "heatmap":  hour_heatmap(reviews, start_dt, end_dt),
        "keywords": top_keywords(reviews, start_dt, end_dt, top_n=top_keywords_n),
        "alerts":   detect_alerts(reviews, start_dt, end_dt, window_days=alerts_window_days).get("alerts", []),
        "revenue":  revenue_proxy_monthly(reviews, start_dt, end_dt, months_back=revenue_months_back),

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
    "last_30_days_block",
]
