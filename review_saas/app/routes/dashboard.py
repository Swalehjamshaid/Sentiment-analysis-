# filename: app/routes/dashboard.py
# ==========================================================
# REVIEW INTELLIGENCE DASHBOARD
# Syntax-SAFE, Contract-SAFE, Time-Series Enhanced
# ==========================================================

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from datetime import datetime
from collections import defaultdict, deque

from app.core.db import get_session
from app.core.models import Review

# main.py already mounts this router with prefix="/api"
router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/ai/insights")
async def analyze_business(
    company_id: int = Query(...),
    start: str = Query(...),
    end: str = Query(...),
    session: AsyncSession = Depends(get_session),
):
    """
    Dashboard analytics provider.
    INPUT AND OUTPUT CONTRACT UNCHANGED.
    """

    # ----------------------------
    # Date parsing (defensive)
    # ----------------------------
    try:
        start_dt = datetime.fromisoformat(start)
        end_dt = datetime.fromisoformat(end)
    except Exception:
        return _empty_dashboard_response()

    # ----------------------------
    # Fetch all reviews safely
    # ----------------------------
    stmt = select(Review).where(
        and_(
            Review.company_id == company_id,
            or_(
                Review.google_review_time.is_(None),
                and_(
                    Review.google_review_time >= start_dt,
                    Review.google_review_time <= end_dt,
                )
            )
        )
    )

    result = await session.execute(stmt)
    reviews = result.scalars().all()
    total_reviews = len(reviews)

    if total_reviews == 0:
        return _empty_dashboard_response()

    # ----------------------------
    # KPIs
    # ----------------------------
    ratings = [r.rating for r in reviews if isinstance(r.rating, (int, float))]
    sentiments = [
        r.sentiment_score
        for r in reviews
        if isinstance(r.sentiment_score, (int, float))
    ]

    avg_rating = round(sum(ratings) / len(ratings), 2) if ratings else 0
    reputation_score = int((avg_rating / 5) * 100) if avg_rating else 0

    # ----------------------------
    # Distribution + emotions
    # ----------------------------
    rating_distribution = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    emotion_buckets = {"Positive": 0, "Neutral": 0, "Negative": 0}

    for r in reviews:
        if r.rating in rating_distribution:
            rating_distribution[r.rating] += 1

        s = r.sentiment_score or 0
        if s >= 0.25:
            emotion_buckets["Positive"] += 1
        elif s <= -0.25:
            emotion_buckets["Negative"] += 1
        else:
            emotion_buckets["Neutral"] += 1

    # ----------------------------
    # Time-series trend (rolling)
    # ----------------------------
    daily_map = defaultdict(list)
    for r in reviews:
        if r.google_review_time:
            day = r.google_review_time.strftime("%Y-%m-%d")
            daily_map[day].append(r.rating or 0)

    ordered_days = sorted(daily_map.keys())
    rolling = deque(maxlen=7)
    sentiment_trend = []

    for day in ordered_days:
        day_avg = round(sum(daily_map[day]) / len(daily_map[day]), 2)
        rolling.append(day_avg)
        rolling_avg = round(sum(rolling) / len(rolling), 2)

        sentiment_trend.append({
            "week": day,
            "avg": rolling_avg
        })

    # ----------------------------
    # Final response (UNCHANGED)
    # ----------------------------
    return {
        "metadata": {
            "total_reviews": total_reviews
        },
        "kpis": {
            "average_rating": avg_rating,
            "reputation_score": reputation_score
        },
        "visualizations": {
            "ratings": rating_distribution,
            "emotions": emotion_buckets,
            "sentiment_trend": sentiment_trend
        }
    }


@router.get("/revenue")
async def revenue_risk(
    company_id: int = Query(...),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(func.avg(Review.rating)).where(
            Review.company_id == company_id
        )
    )
    avg = result.scalar() or 0

    if avg >= 4:
        return {"risk_percent": 10, "impact": "Low"}
    elif avg >= 3:
        return {"risk_percent": 40, "impact": "Medium"}
    return {"risk_percent": 80, "impact": "High"}


def _empty_dashboard_response():
    return JSONResponse({
        "metadata": {
            "total_reviews": 0
        },
        "kpis": {
            "average_rating": 0,
            "reputation_score": 0
        },
        "visualizations": {
            "ratings": {1: 0, 2: 0, 3: 0, 4: 0, 5: 0},
            "emotions": {
                "Positive": 0,
                "Neutral": 0,
                "Negative": 0
            },
            "sentiment_trend": []
        }
    })
``
