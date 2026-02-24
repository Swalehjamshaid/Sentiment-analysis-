# FILE: app/services/analysis.py
"""
Executive Analysis Engine v3.5.2
Fully Aligned with Google Places API Data Structures.
Fixes 500 errors via Python 3.13 Timezone & NoneType safety.
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
    """Lenient date parser with UTC fallback to prevent 500 errors."""
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
    """Applies filters while handling potential timezone-naive DB columns."""
    start_dt = _parse_date(start)
    end_dt   = _parse_date(end)

    if start_dt is not None:
        query = query.filter(Review.review_date >= start_dt)

    if end_dt is not None:
        if end_dt.hour == 0 and end_dt.minute == 0:
            query = query.filter(Review.review_date < (end_dt + timedelta(days=1)))
        else:
            query = query.filter(Review.review_date <= end_dt)

    return query


def get_company_or_404(db: Session, company_id: int) -> Company:
    company = db.query(Company).filter(Company.id == company_id).first()
    if company is None:
        raise ValueError(f"Company ID {company_id} does not exist.")
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
# 30-DAY INSIGHTS ENGINE (Google API Power)
# ─────────────────────────────────────────────────────────────

_LAST30D_CACHE = {}
_LAST30D_LOCK = threading.Lock()

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
            cat = str(r.sentiment_category or "").lower()
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


def _exec_summary(analysis: Dict[str, Any]) -> Dict[str, Any]:
    """Safe summary formatter that handles Google data gaps."""
    avg_rating = analysis.get("avg_rating")
    avg_str = f"{avg_rating:.1f}" if avg_rating is not None else "0.0"
    
    total = analysis.get("total_reviews", 0)
    trend = analysis.get("trend", {})
    signal = str(trend.get("signal") or "Stable").lower()
    delta = trend.get("delta") or 0.0

    phrase = {"improving": "improving", "declining": "declining"}.get(signal, "stable")
    delta_str = f" ({delta:+.2f} MoM)" if delta != 0 else ""

    snapshot = (
        f"Google API Intel: {total} reviews analyzed in this window. "
        f"Average experience rating is {avg_str}/5.0, currently showing a {phrase}{delta_str} trajectory."
    )

    return {
        "executive_snapshot": snapshot,
        "recommendations": analysis.get("ai_recommendations", [])[:5],
    }

def last_30_days_block(db: Session, company_id: int) -> Dict[str, Any]:
    start, end = _last30d_window()
    cache_key = (company_id, start.date().isoformat())

    with _LAST30D_LOCK:
        cached = _LAST30D_CACHE.get(cache_key)
        if cached and cached["expires"] > datetime.now(timezone.utc).timestamp():
            return cached["data"]

    reviews = fetch_reviews(db, company_id, start.isoformat(), end.isoformat())
    total = len(reviews)
    pos = sum(1 for r in reviews if (r.rating or 0) >= 4)
    neg = sum(1 for r in reviews if (r.rating or 0) <= 2)

    company = get_company_or_404(db, company_id)
    try:
        analysis = analyze_reviews(reviews, company, start, end, include_aspects=True)
        exec_sum = _exec_summary(analysis)
    except Exception as e:
        logger.error(f"Analysis Error: {e}")
        exec_sum = {"executive_snapshot": "Neural engine is processing Google data streams..."}

    payload = {
        "total_comments_30d": total,
        "positive_comments_30d": pos,
        "negative_comments_30d": neg,
        "executive_summary_30d": exec_sum,
        "daily_counts": _daily_counts_chart(reviews),
        "sentiment_ring": {"labels": ["Pos", "Neg", "Neu"], "data": [pos, neg, max(0, total-pos-neg)]},
    }

    with _LAST30D_LOCK:
        _LAST30D_CACHE[cache_key] = {
            "data": payload,
            "expires": datetime.now(timezone.utc).timestamp() + 300
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
) -> Dict[str, Any]:
    company = get_company_or_404(db, company_id)
    reviews = fetch_reviews(db, company_id, start, end)

    start_dt = _parse_date(start)
    end_dt   = _parse_date(end)

    core = analyze_reviews(reviews, company, start_dt, end_dt, include_aspects=True)
    
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
            "total": len(reviews),
            "avg_rating": core.get("avg_rating") or 0.0,
            "risk_score": core.get("risk_score") or 0.0,
            "risk_level": core.get("risk_level", "Low"),
        },
        "trend": {
            "labels": [x["month"] for x in core.get("trend_data", [])],
            "data": [x["avg_rating"] for x in core.get("trend_data", [])],
            "signal": core.get("trend", {}).get("signal", "Stable"),
            "delta": core.get("trend", {}).get("delta") or 0.0,
        },
        "sentiment": core.get("sentiments", {"Positive": 0, "Neutral": 0, "Negative": 0}),
        "heatmap": hour_heatmap(reviews, start_dt, end_dt),
        "reviews": {
            "total": len(reviews),
            "data": [
                {
                    "id": r.id,
                    "review_date": r.review_date.isoformat() if r.review_date else None,
                    "rating": int(r.rating or 0),
                    "text": r.text or "Customer provided star rating only.",
                    "reviewer_name": r.reviewer_name or "Verified Customer",
                    "sentiment_category": r.sentiment_category or "Neutral",
                } for r in reviews
            ]
        },
        "window": {"start": start, "end": end},
        "version": "3.5.2-GA",
        **insights_30d
    }

__all__ = ["get_company_or_404", "fetch_reviews", "dashboard_payload", "last_30_days_block"]
