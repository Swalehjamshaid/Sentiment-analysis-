# FILE: app/services/analysis.py
"""
analysis.py
-----------
Database Aggregation Layer for dashboard.html

This module connects:
- DATABASE (Company + Reviews ORM)
- AI Insights Engine (ai_insights.py)
- Dashboard API (routes/dashboard.py)

Responsibilities:
- Fetch & filter data from DB
- Aggregate data for charts/widgets
- Convert ORM → Python dict forms required by dashboard.html
- Call ai_insights.py for deep NLP analytics
- Provide unified dashboard payload
"""

from __future__ import annotations
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta

from sqlalchemy.orm import Session
from sqlalchemy import func, or_

from app.models import Company, Review
from app.services.ai_insights import (
    metrics_payload,
    trend_timeseries,
    sentiment_buckets,
    sources_breakdown,
    hour_heatmap,
    top_keywords,
    detect_alerts,
    revenue_proxy_monthly,
    analyze_reviews,
)

# -------------------------------------------------------
# Helpers
# -------------------------------------------------------

def _parse_date(s: Optional[str]) -> Optional[datetime]:
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


def get_company_or_404(db: Session, company_id: int) -> Company:
    c = db.query(Company).filter(Company.id == company_id).first()
    if not c:
        raise ValueError("Company not found")
    return c


def fetch_reviews(db: Session, company_id: int, start: Optional[str], end: Optional[str]):
    q = db.query(Review).filter(Review.company_id == company_id)
    q = _apply_date_filter(q, start, end)
    return q.all()


# -------------------------------------------------------
# Dashboard Blocks (Single Responsibility)
# -------------------------------------------------------

def metrics_block(db: Session, company_id: int, start: str | None, end: str | None):
    rows = fetch_reviews(db, company_id, start, end)
    return metrics_payload(rows, _parse_date(start), _parse_date(end))


def trend_block(db: Session, company_id: int, start: str | None, end: str | None):
    rows = fetch_reviews(db, company_id, start, end)
    return trend_timeseries(rows, _parse_date(start), _parse_date(end))


def sentiment_block(db: Session, company_id: int, start: str | None, end: str | None):
    rows = fetch_reviews(db, company_id, start, end)
    return sentiment_buckets(rows, _parse_date(start), _parse_date(end))


def sources_block(db: Session, company_id: int, start: str | None, end: str | None):
    rows = fetch_reviews(db, company_id, start, end)
    return sources_breakdown(rows, _parse_date(start), _parse_date(end))


def heatmap_block(db: Session, company_id: int, start: str | None, end: str | None):
    rows = fetch_reviews(db, company_id, start, end)
    return hour_heatmap(rows, _parse_date(start), _parse_date(end))


def keywords_block(db: Session, company_id: int, start: str | None, end: str | None, top_n: int = 20):
    rows = fetch_reviews(db, company_id, start, end)
    return top_keywords(rows, _parse_date(start), _parse_date(end), top_n=top_n)


def alerts_block(db: Session, company_id: int, start: str | None, end: str | None, window: int = 14):
    rows = fetch_reviews(db, company_id, start, end)
    return detect_alerts(rows, _parse_date(start), _parse_date(end), window_days=window)


def revenue_block(db: Session, company_id: int, start: str | None, end: str | None, months: int = 6):
    rows = fetch_reviews(db, company_id, start, end)
    return revenue_proxy_monthly(rows, _parse_date(start), _parse_date(end), months_back=months)


# -------------------------------------------------------
# Server-side DataTable for dashboard.html
# -------------------------------------------------------

def reviews_table(db: Session, company_id: int, page=1, limit=25, search=None,
                  sort="review_date", order="desc", start=None, end=None):

    q = db.query(Review).filter(Review.company_id == company_id)
    q = _apply_date_filter(q, start, end)

    if search:
        s = f"%{search}%"
        q = q.filter(or_(
            Review.text.ilike(s),
            Review.reviewer_name.ilike(s),
            Review.keywords.ilike(s),
            Review.sentiment_category.ilike(s)
        ))

    total = q.count()

    if not hasattr(Review, sort):
        sort = "review_date"

    col = getattr(Review, sort)
    q = q.order_by(col.desc() if order == "desc" else col.asc())

    offset = (page - 1) * limit
    rows = q.offset(offset).limit(limit).all()

    data = [{
        "id": r.id,
        "date": r.review_date.isoformat() if r.review_date else None,
        "rating": r.rating,
        "text": r.text,
        "reviewer": r.reviewer_name,
        "sentiment": r.sentiment_category,
        "keywords": r.keywords,
    } for r in rows]

    from math import ceil
    return {
        "page": page,
        "limit": limit,
        "total": total,
        "pages": ceil(total / limit),
        "data": data,
    }


# -------------------------------------------------------
# FULL DASHBOARD PAYLOAD
# (Single API call → dashboard.html hydration)
# -------------------------------------------------------

def dashboard_payload(db: Session, company_id: int, start=None, end=None):
    company = get_company_or_404(db, company_id)
    reviews = fetch_reviews(db, company_id, start, end)

    insights = analyze_reviews(reviews, company, _parse_date(start), _parse_date(end))

    return {
        "company": {
            "id": company.id,
            "name": company.name,
            "city": company.city,
            "status": company.status,
        },
        "metrics": metrics_payload(reviews, _parse_date(start), _parse_date(end)),
        "trend": trend_timeseries(reviews, _parse_date(start), _parse_date(end)),
        "sentiment": sentiment_buckets(reviews, _parse_date(start), _parse_date(end)),
        "sources": sources_breakdown(reviews, _parse_date(start), _parse_date(end)),
        "heatmap": hour_heatmap(reviews, _parse_date(start), _parse_date(end)),
        "keywords": top_keywords(reviews, _parse_date(start), _parse_date(end)),
        "alerts": detect_alerts(reviews, _parse_date(start), _parse_date(end))["alerts"],
        "revenue": revenue_proxy_monthly(reviews, _parse_date(start), _parse_date(end)),
        "daily_series": insights["daily_series"],
        "aspects": insights["aspects"],
        "ai_recommendations": insights["ai_recommendations"],
        "window": insights["window"],
        "payload_version": insights["payload_version"],
    }


__all__ = [
    "dashboard_payload",
    "metrics_block",
    "trend_block",
    "sentiment_block",
    "sources_block",
    "heatmap_block",
    "keywords_block",
    "alerts_block",
    "revenue_block",
    "reviews_table",
    "fetch_reviews",
    "get_company_or_404",
]
