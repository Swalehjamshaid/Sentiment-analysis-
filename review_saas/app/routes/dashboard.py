from __future__ import annotations
import logging
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

from fastapi import APIRouter, Query, Request
from sqlalchemy import and_, func, select, desc, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.models import Company, Review
from app.services.sentiment import analyze_full_review # Using your VADER logic

router = APIRouter(prefix="/api", tags=["dashboard"])
logger = logging.getLogger("app.dashboard")

# ──────────────────────────────────────────────────────────────────────────────
# Utilities
# ──────────────────────────────────────────────────────────────────────────────

def _range_or_default(start: Optional[str], end: Optional[str]) -> Tuple[date, date]:
    today = date.today()
    end_dt = datetime.strptime(end, "%Y-%m-%d").date() if end else today
    start_dt = datetime.strptime(start, "%Y-%m-%d").date() if start else (end_dt - timedelta(days=29))
    return start_dt, end_dt

# ──────────────────────────────────────────────────────────────────────────────
# Primary Dashboard Endpoints
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/kpis")
async def api_kpis(company_id: int, start: Optional[str] = None, end: Optional[str] = None):
    s, e = _range_or_default(start, end)
    async with get_session() as session:
        # Calculate standard KPIs
        stmt = select(
            func.count(Review.id).label("total"),
            func.avg(Review.rating).label("rating"),
            func.avg(Review.sentiment_score).label("sentiment")
        ).where(and_(
            Review.company_id == company_id,
            Review.google_review_time >= s,
            Review.google_review_time <= e
        ))
        res = (await session.execute(stmt)).first()
        
        # New reviews in last 7 days
        new_stmt = select(func.count(Review.id)).where(and_(
            Review.company_id == company_id,
            Review.google_review_time >= (e - timedelta(days=7))
        ))
        new_count = (await session.execute(new_stmt)).scalar() or 0

        return {
            "total_reviews": res.total or 0,
            "avg_rating": round(float(res.rating or 0.0), 1),
            "avg_sentiment": round(float(res.sentiment or 0.0), 3),
            "new_reviews": new_count
        }

@router.get("/series/overview")
async def api_series_overview(company_id: int, start: Optional[str] = None, end: Optional[str] = None):
    s, e = _range_or_default(start, end)
    async with get_session() as session:
        # Group by date for Volume, Rating, and Sentiment
        stmt = select(
            func.date(Review.google_review_time).label("date"),
            func.count(Review.id).label("volume"),
            func.avg(Review.rating).label("rating"),
            func.avg(Review.sentiment_score).label("sentiment")
        ).where(and_(
            Review.company_id == company_id,
            Review.google_review_time >= s,
            Review.google_review_time <= e
        )).group_by("date").order_by("date")
        
        res = await session.execute(stmt)
        rows = res.all()
        
        return {
            "volume": [{"date": str(r.date), "value": r.volume} for r in rows],
            "rating": [{"date": str(r.date), "value": round(float(r.rating), 2)} for r in rows],
            "sentiment": [{"date": str(r.date), "value": round(float(r.sentiment), 3)} for r in rows]
        }

@router.get("/v2/ai/executive-summary")
async def executive_summary_v2(company_id: int, start: Optional[str] = None, end: Optional[str] = None):
    # This matches the "conclusion_box" and "ai_summary" IDs in your HTML
    kpis = await api_kpis(company_id, start, end)
    
    avg_sent = kpis["avg_sentiment"]
    conclusion = "On Track"
    if avg_sent > 0.4: conclusion = "Strong Momentum"
    elif avg_sent < 0.1: conclusion = "Needs Attention"
    
    return {
        "summary": f"Analyzed {kpis['total_reviews']} reviews. Overall sentiment is holding at {avg_sent}.",
        "conclusion": conclusion,
        "top_actions": ["Monitor recent complaints", "Boost 5-star review velocity"]
    }

@router.get("/keywords/themes")
async def api_keywords_themes(company_id: int, start: Optional[str] = None, end: Optional[str] = None):
    # Hardcoded for now, but usually involves text processing logic
    return {
        "positive_keywords": ["staff", "clean", "location"],
        "negative_keywords": ["price", "wait time"],
        "emerging": ["delivery", "app support"]
    }

@router.get("/reviews/feed")
async def api_reviews_feed(company_id: int, start: Optional[str] = None, end: Optional[str] = None):
    s, e = _range_or_default(start, end)
    async with get_session() as session:
        stmt = select(Review).where(and_(
            Review.company_id == company_id,
            Review.google_review_time >= s,
            Review.google_review_time <= e
        )).order_by(desc(Review.google_review_time)).limit(20)
        
        res = await session.execute(stmt)
        reviews = res.scalars().all()
        
        return {
            "items": [{
                "author_name": r.author_name,
                "rating": r.rating,
                "text": r.text,
                "sentiment_label": r.sentiment_label,
                "review_time": str(r.google_review_time.date()),
                "is_urgent": r.rating <= 2 # Logic to trigger red highlight in HTML
            } for r in reviews]
        }

@router.get("/ratings/distribution")
async def api_ratings_distribution(company_id: int, start: Optional[str] = None, end: Optional[str] = None):
    s, e = _range_or_default(start, end)
    async with get_session() as session:
        stmt = select(Review.rating, func.count(Review.id)).where(and_(
            Review.company_id == company_id,
            Review.google_review_time >= s,
            Review.google_review_time <= e
        )).group_by(Review.rating)
        
        res = await session.execute(stmt)
        dist = {1:0, 2:0, 3:0, 4:0, 5:0}
        for rating, count in res.all():
            dist[rating] = count
        return {"distribution": dist}
