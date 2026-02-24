# FILE: app/services/analysis.py
"""
Database-aware analysis helpers aligned to app/models.py structures.
Integrated 30-Day Insights Engine with safe-fail defaults.
"""

from __future__ import annotations

import math
import logging
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

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# Date & Filter Utilities
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
# NEW: 30-DAY INSIGHTS ENGINE
# ─────────────────────────────────────────────────────────────

_LAST30D_CACHE = {}
_LAST30D_LOCK = threading.Lock()
_LAST30D_TTL_SECONDS = int(os.getenv("LAST30D_TTL_SECONDS", "300"))


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
            cat = (r.sentiment_category or "").lower()
            if cat == "positive":
                by_date[key]["positive"] += 1
            elif cat == "negative":
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
        "datasets": {"total": totals, "positive": positives, "negative": negatives}
    }


def _sentiment_ring(total: int, pos: int, neg: int):
    neutral = max(total - pos - neg, 0)
    return {
        "labels": ["Positive", "Negative", "Neutral"],
        "data": [pos, neg, neutral],
    }


def _exec_summary(analysis: Dict[str, Any]) -> Dict[str, Any]:
    avg_rating = analysis.get("avg_rating") or 0.0
    total = analysis.get("total_reviews", 0)
    trend = analysis.get("trend", {})
    signal = (trend.get("signal") or "Stable").lower()
    delta = trend.get("delta") or 0.0

    phrase = {"improving": "improving", "declining": "declining", "stable": "stable"}.get(signal, "steady")
    delta_str = f" ({delta:+.2f} MoM)" if delta != 0.0 else ""

    snapshot = (
        f"Last 30 days captured {total} review(s). Average rating is {avg_rating:.2f}, sentiment is {phrase}{delta_str}."
    )

    aspects = analysis.get("aspects", [])
    pos_aspects = [a for a in aspects if a.get("polarity") == "positive"][:3]
    neg_aspects = [a for a in aspects if a.get("polarity") == "negative"][:3]

    return {
        "executive_snapshot": snapshot,
        "patterns": [f"{a['aspect']}: {a.get('count')} mentions" for a in (pos_aspects[:2] + neg_aspects[:1])],
        "risks": [f"{a['aspect']} - attention required" for a in neg_aspects],
        "opportunities": [f"{a['aspect']} - performing well" for a in pos_aspects],
        "recommendations": analysis.get("ai_recommendations", [])[:5],
    }


def last_30_days_block(db: Session, company_id: int) -> Dict[str, Any]:
    start, end = _last30d_window()
    cache_key = (company_id, start.date().isoformat(), end.date().isoformat())

    with _LAST30D_LOCK:
        cached = _LAST30D_CACHE.get(cache_key)
        if cached and cached["expires"] > datetime.now(timezone.utc).timestamp():
            return cached["data"]

    reviews = fetch_reviews(db, company_id, start.isoformat(), end.isoformat())
    total = len(reviews)
    pos = sum(1 for r in reviews if (r.sentiment_category or "").lower() == "positive")
    neg = sum(1 for r in reviews if (r.sentiment_category or "").lower() == "negative")

    company = get_company_or_404(db, company_id)
    analysis = analyze_reviews(reviews, company, start, end, include_aspects=True)

    payload = {
        "total_comments_30d": total,
        "positive_comments_30d": pos,
        "negative_comments_30d": neg,
        "ai_summary_30d": analysis.get("ai_recommendations", []),
        "executive_summary_30d": _exec_summary(analysis),
        "daily_counts": _daily_counts_chart(reviews),
        "sentiment_ring": _sentiment_ring(total, pos, neg),
    }

    with _LAST30D_LOCK:
        _LAST30D_CACHE[cache_key] = {
            "data": payload,
            "expires": datetime.now(timezone.utc).timestamp() + _LAST30D_TTL_SECONDS
        }
    return payload

# ─────────────────────────────────────────────────────────────
# Unified Dashboard Payload
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

    core_analysis = analyze_reviews(reviews, company, start_dt, end_dt, include_aspects=True)
    
    # Safely fetch 30-day block
    try:
        insights_30d = last_30_days_block(db, company_id)
    except Exception as e:
        logger.error(f"30d block failed: {e}")
        insights_30d = {}

    return {
        "company": {
            "id": company.id,
            "name": company.name,
            "city": company.city,
            "status": company.status,
        },
        "metrics": {
            "total": core_analysis.get("total_reviews", 0),
            "avg_rating": core_analysis.get("avg_rating") or 0.0,
            "risk_score": core_analysis.get("risk_score") or 0.0,
            "risk_level": core_analysis.get("risk_level", "Low"),
        },
        "trend": {
            "labels": [x["month"] for x in core_analysis.get("trend_data", [])],
            "data": [x["avg_rating"] for x in core_analysis.get("trend_data", [])],
            "signal": core_analysis.get("trend", {}).get("signal", "Stable"),
            "delta": core_analysis.get("trend", {}).get("delta") or 0.0,
        },
        "sentiment": core_analysis.get("sentiments", {"Positive": 0, "Neutral": 0, "Negative": 0}),
        "daily_series": core_analysis.get("daily_series", []),
        "aspects": core_analysis.get("aspects", []),
        "ai_recommendations": core_analysis.get("ai_recommendations", []),
        "heatmap": hour_heatmap(reviews, start_dt, end_dt),
        "reviews": {
            "total": len(reviews),
            "data": [
                {
                    "id": r.id,
                    "review_date": r.review_date.isoformat() if r.review_date else None,
                    "rating": int(r.rating or 0),
                    "text": r.text or "",
                    "reviewer_name": r.reviewer_name,
                    "sentiment_category": r.sentiment_category,
                } for r in reviews
            ]
        },
        "window": core_analysis.get("window", {}),
        "version": "3.5",
        **insights_30d
    }

__all__ = [
    "get_company_or_404", "fetch_reviews", "dashboard_payload", "last_30_days_block"
]
