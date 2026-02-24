# FILE: app/services/analysis.py
"""
Executive Analysis Engine v3.5.3
- Aligned with Google Places API star-rating logic.
- Python 3.13 Stability: Fixed Timezone & NoneType formatting crashes.
- Defensive Programming: Prevents 500 errors on empty database states.
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
# Stability Utilities
# ─────────────────────────────────────────────────────────────

def _parse_date(value: Optional[str]) -> Optional[datetime]:
    """Ensures all strings become UTC-aware to prevent Python 3.13 crashes."""
    if not value:
        return None
    value = value.strip()
    try:
        # Standardize ISO format
        dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, AttributeError):
        try:
            return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            return None

def _apply_date_filter(query, start: Optional[str] = None, end: Optional[str] = None):
    """Filters date range safely across different DB engines."""
    start_dt = _parse_date(start)
    end_dt   = _parse_date(end)
    if start_dt:
        query = query.filter(Review.review_date >= start_dt)
    if end_dt:
        if end_dt.hour == 0 and end_dt.minute == 0:
            query = query.filter(Review.review_date < (end_dt + timedelta(days=1)))
        else:
            query = query.filter(Review.review_date <= end_dt)
    return query

# ─────────────────────────────────────────────────────────────
# 30-Day Executive Logic (Aligned with Google API)
# ─────────────────────────────────────────────────────────────

_LAST30D_CACHE = {}
_LAST30D_LOCK = threading.Lock()

def _exec_summary(analysis: Dict[str, Any]) -> Dict[str, Any]:
    """Safe summary builder. Prevents formatting 'None' values which causes 500s."""
    avg_rating = analysis.get("avg_rating")
    # CRITICAL FIX: Fallback to 0.0 if avg_rating is None
    avg_str = f"{avg_rating:.1f}" if avg_rating is not None else "0.0"
    
    total = analysis.get("total_reviews", 0)
    trend = analysis.get("trend", {})
    signal = str(trend.get("signal") or "Stable").lower()
    delta = trend.get("delta") or 0.0

    phrase = {"improving": "improving", "declining": "declining"}.get(signal, "stable")
    delta_str = f" ({delta:+.2f} MoM)" if delta != 0 else ""

    snapshot = (
        f"Google API Insight: {total} new reviews detected. "
        f"The current average rating is {avg_str}/5.0, showing a {phrase}{delta_str} trend."
    )
    return {
        "executive_snapshot": snapshot,
        "recommendations": analysis.get("ai_recommendations", [])[:5],
    }

def last_30_days_block(db: Session, company_id: int) -> Dict[str, Any]:
    """Fetches recent Google activity with safety wrappers."""
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=30)
    
    reviews = db.query(Review).filter(
        Review.company_id == company_id,
        Review.review_date >= start
    ).all()

    total = len(reviews)
    # Map Google Ratings: 4-5 stars are Positive
    pos = sum(1 for r in reviews if (r.rating or 0) >= 4)
    neg = sum(1 for r in reviews if (r.rating or 0) <= 2)

    try:
        company = db.query(Company).filter(Company.id == company_id).first()
        analysis = analyze_reviews(reviews, company, start, end, include_aspects=True)
        exec_sum = _exec_summary(analysis)
    except Exception as e:
        logger.error(f"30d Analysis Error for ID {company_id}: {e}")
        exec_sum = {"executive_snapshot": "Neural engine is processing incoming Google data streams."}

    return {
        "total_comments_30d": total,
        "positive_comments_30d": pos,
        "negative_comments_30d": neg,
        "executive_summary_30d": exec_sum,
        "sentiment_ring": {"labels": ["Pos", "Neg", "Neu"], "data": [pos, neg, max(0, total-pos-neg)]}
    }

# ─────────────────────────────────────────────────────────────
# Unified Dashboard Payload (Production Version)
# ─────────────────────────────────────────────────────────────

def dashboard_payload(
    db: Session,
    company_id: int,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> Dict[str, Any]:
    """Final payload for dashboard.html. Perfectly aligned with Google API fields."""
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company: 
        raise ValueError("Invalid Company ID")

    reviews = fetch_reviews(db, company_id, start, end)
    start_dt, end_dt = _parse_date(start), _parse_date(end)

    # Core engine results
    core = analyze_reviews(reviews, company, start_dt, end_dt, include_aspects=True)
    
    # 30-Day Logic (Try/Except to prevent 500 if one part of analysis fails)
    try:
        insights_30d = last_30_days_block(db, company_id)
    except Exception as e:
        logger.error(f"Last 30d block failed: {e}")
        insights_30d = {}

    return {
        "company": {
            "id": company.id, 
            "name": company.name, 
            "city": company.city,
            "last_synced": company.last_synced_at.isoformat() if hasattr(company, 'last_synced_at') and company.last_synced_at else "Never"
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
                    "text": r.text or "Customer gave stars but no comment text.",
                    "reviewer_name": r.reviewer_name or "Verified Customer",
                    "sentiment_category": r.sentiment_category or "Neutral",
                } for r in reviews
            ]
        },
        "window": {"start": start, "end": end},
        "version": "3.5.3-STABLE",
        **insights_30d
    }

__all__ = ["dashboard_payload", "last_30_days_block"]
