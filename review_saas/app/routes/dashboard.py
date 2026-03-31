# filename: app/routes/dashboard.py
# ✅ Fully aligned with models.py, db.py, dashboard.html

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime
from collections import defaultdict

from app.core.db import get_session
from app.core.models import Review

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


# =====================================================
# ANALYZE BUSINESS (MAIN DASHBOARD DATA)
# =====================================================

@router.get("/ai/insights")
async def dashboard_insights(
    company_id: int = Query(...),
    start: str = Query(...),
    end: str = Query(...),
    session: AsyncSession = Depends(get_session),
):
    """
    Provides all data required by dashboard.html.
    Frontend renders charts; backend aggregates raw data.
    """

    # ---------------------------
    # Parse dates from frontend
    # ---------------------------
    try:
        start_dt = datetime.fromisoformat(start)
        end_dt = datetime.fromisoformat(end)
    except Exception:
        return JSONResponse({
            "metadata": {"total_reviews": 0},
            "kpis": {"average_rating": 0, "reputation_score": 0},
            "visualizations": {
                "ratings": {1:0,2:0,3:0,4:0,5:0},
                "sentiment_trend": [],
                "emotions": {"Positive":0,"Neutral":0,"Negative":0}
            }
        })

    # ---------------------------
    # Fetch reviews (✅ correct column)
    # ---------------------------
    result = await session.execute(
        select(Review).where(
            Review.company_id == company_id,
            Review.google_review_time >= start_dt,
            Review.google_review_time <= end_dt
        )
    )

    reviews = result.scalars().all()
    total = len(reviews)

    if total == 0:
        return JSONResponse({
            "metadata": {"total_reviews": 0},
            "kpis": {"average_rating": 0, "reputation_score": 0},
            "visualizations": {
                "ratings": {1:0,2:0,3:0,4:0,5:0},
                "sentiment_trend": [],
                "emotions": {"Positive":0,"Neutral":0,"Negative":0}
            }
        })

    # ---------------------------
    # KPI calculations
    # ---------------------------
    avg_rating = round(
        sum((r.rating or 0) for r in reviews) / total, 2
    )
    reputation_score = round((avg_rating / 5) * 100, 0)

    # ---------------------------
    # Rating distribution
    # ---------------------------
    ratings = {1:0,2:0,3:0,4:0,5:0}
    emotions = {"Positive":0, "Neutral":0, "Negative":0}
    trend_map = defaultdict(list)

    for r in reviews:
        if r.rating in ratings:
            ratings[r.rating] += 1

        score = r.sentiment_score or 0
        if score >= 0.25:
            emotions["Positive"] += 1
        elif score <= -0.25:
            emotions["Negative"] += 1
        else:
            emotions["Neutral"] += 1

        day_key = r.google_review_time.strftime("%Y-%m-%d")
        trend_map[day_key].append(r.rating or 0)

    sentiment_trend = [
        {"week": day, "avg": round(sum(vals)/len(vals), 2)}
        for day, vals in sorted(trend_map.items())
    ]

    return {
        "metadata": {
            "total_reviews": total
        },
        "kpis": {
            "average_rating": avg_rating,
            "reputation_score": reputation_score
        },
        "visualizations": {
            "ratings": ratings,
            "emotions": emotions,
            "sentiment_trend": sentiment_trend
        }
    }


# =====================================================
# REVENUE RISK (USED BY DASHBOARD)
# =====================================================

@router.get("/revenue")
async def revenue_risk(
    company_id: int,
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
    else:
        return {"risk_percent": 80, "impact": "High"}
