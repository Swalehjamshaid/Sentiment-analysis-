from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime
from collections import defaultdict, Counter

from app.core.db import get_session
from app.core.models import Review

# main.py mounts router with prefix="/api"
# -> final paths are /api/dashboard/...
router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


# -----------------------------
# Helpers
# -----------------------------
def safe_avg(values):
    return round(sum(values) / len(values), 2) if values else 0.0


def month_label(dt):
    return dt.strftime("%b %Y")


# -----------------------------
# MAIN DASHBOARD ENDPOINT
# -----------------------------
@router.get("/ai/insights")
async def dashboard_insights(
    company_id: int = Query(...),
    start: str | None = Query(None),
    end: str | None = Query(None),
    amp_start: str | None = Query(None, alias="amp;start"),
    amp_end: str | None = Query(None, alias="amp;end"),
    db: AsyncSession = Depends(get_session),
):
    start_val = start or amp_start
    end_val = end or amp_end

    try:
        start_dt = datetime.fromisoformat(start_val) if start_val else None
        end_dt = datetime.fromisoformat(end_val) if end_val else None
    except Exception:
        start_dt = None
        end_dt = None

    stmt = select(Review).where(Review.company_id == company_id)

    if start_dt and end_dt:
        stmt = stmt.where(
            Review.google_review_time >= start_dt,
            Review.google_review_time <= end_dt,
        )

    result = await db.execute(stmt)
    reviews = result.scalars().all()

    if not reviews:
        return _empty_dashboard()

    ratings = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    emotions = {"Positive": 0, "Neutral": 0, "Negative": 0}
    trend_map = defaultdict(list)
    words = []

    for r in reviews:
        if r.rating in ratings:
            ratings[r.rating] += 1

        score = r.sentiment_score or 0.0
        if score >= 0.25:
            emotions["Positive"] += 1
        elif score <= -0.25:
            emotions["Negative"] += 1
        else:
            emotions["Neutral"] += 1

        if r.google_review_time:
            trend_map[month_label(r.google_review_time)].append(r.rating or 0)

        if r.text:
            words.extend(r.text.lower().split())

    sentiment_trend = [
        {"week": k, "avg": safe_avg(v)}
        for k, v in sorted(trend_map.items())
    ]

    avg_rating = safe_avg([r.rating for r in reviews if r.rating])

    keywords = [
        {"text": k, "value": v}
        for k, v in Counter(words).most_common(15)
    ]

    return {
        "metadata": {"total_reviews": len(reviews)},
        "kpis": {
            "average_rating": avg_rating,
            "reputation_score": avg_rating,
        },
        "visualizations": {
            "ratings": ratings,
            "emotions": emotions,
            "sentiment_trend": sentiment_trend,
            "keywords": keywords,
        },
    }


# -----------------------------
# REVENUE RISK
# -----------------------------
@router.get("/revenue")
async def revenue_risk(
    company_id: int = Query(...),
    db: AsyncSession = Depends(get_session),
):
    result = await db.execute(
        select(func.avg(Review.rating)).where(Review.company_id == company_id)
    )
    avg_rating = result.scalar() or 0.0

    if avg_rating >= 4:
        return {"risk_percent": 10, "impact": "Low"}
    elif avg_rating >= 3:
        return {"risk_percent": 40, "impact": "Medium"}
    return {"risk_percent": 80, "impact": "High"}


# -----------------------------
# EMPTY FALLBACK
# -----------------------------
def _empty_dashboard():
    return JSONResponse({
        "metadata": {"total_reviews": 0},
        "kpis": {"average_rating": 0, "reputation_score": 0},
        "visualizations": {
            "ratings": {1: 0, 2: 0, 3: 0, 4: 0, 5: 0},
            "emotions": {"Positive": 0, "Neutral": 0, "Negative": 0},
            "sentiment_trend": [],
            "keywords": [],
        },
    })
``
