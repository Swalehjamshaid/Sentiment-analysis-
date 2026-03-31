# filename: app/routes/dashboard.py
# ==========================================================
# REVIEW INTELLIGENCE DASHBOARD (FINAL ✅)
# ==========================================================

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime
from collections import defaultdict

from app.core.db import get_session
from app.core.models import Review

# ✅ IMPORTANT:
# main.py already uses prefix="/api"
# so we MUST NOT repeat "/api" here
router = APIRouter(prefix="/dashboard", tags=["dashboard"])

# ==========================================================
# ANALYZE BUSINESS (MAIN DASHBOARD ENDPOINT)
# ==========================================================

@router.get("/ai/insights")
async def analyze_business(
    company_id: int = Query(...),
    start: str = Query(...),
    end: str = Query(...),
    session: AsyncSession = Depends(get_session),
):
    """
    Backend data provider for dashboard.html.
    Frontend handles visualization (Chart.js).
    """

    # ------------------------------------------------------
    # Parse dates safely (frontend uses YYYY-MM-DD)
    # ------------------------------------------------------
    try:
        start_dt = datetime.fromisoformat(start)
        end_dt = datetime.fromisoformat(end)
    except Exception:
        return _empty_dashboard_response()

    # ------------------------------------------------------
    # Fetch reviews from PostgreSQL (✅ correct column)
    # ------------------------------------------------------
    result = await session.execute(
        select(Review).where(
            Review.company_id == company_id,
            Review.google_review_time >= start_dt,
            Review.google_review_time <= end_dt
        )
    )
    reviews = result.scalars().all()

    total_reviews = len(reviews)

    if total_reviews == 0:
        return _empty_dashboard_response()

    # ------------------------------------------------------
    # KPI calculations
    # ------------------------------------------------------
    avg_rating = round(
        sum((r.rating or 0) for r in reviews) / total_reviews,
        2
    )

    reputation_score = int((avg_rating / 5) * 100)

    # ------------------------------------------------------
    # Rating distribution (BAR chart)
    # ------------------------------------------------------
    ratings = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    emotions = {"Positive": 0, "Neutral": 0, "Negative": 0}
    trend_map = defaultdict(list)

    for r in reviews:
        if r.rating in ratings:
            ratings[r.rating] += 1

        # sentiment buckets
        score = r.sentiment_score or 0
        if score >= 0.25:
            emotions["Positive"] += 1
        elif score <= -0.25:
            emotions["Negative"] += 1
        else:
            emotions["Neutral"] += 1

        # sentiment trend by date
        day = r.google_review_time.strftime("%Y-%m-%d")
        trend_map[day].append(r.rating or 0)

    sentiment_trend = [
        {"week": d, "avg": round(sum(vals) / len(vals), 2)}
        for d, vals in sorted(trend_map.items())
    ]

    # ------------------------------------------------------
    # FINAL RESPONSE (MATCHES dashboard.html EXACTLY)
    # ------------------------------------------------------
    return {
        "metadata": {
            "total_reviews": total_reviews
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


# ==========================================================
# REVENUE RISK MONITORING
# ==========================================================

@router.get("/revenue")
async def revenue_risk(
    company_id: int = Query(...),
    session: AsyncSession = Depends(get_session),
):
    """
    Used by dashboard.html Revenue Risk card.
    """

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


# ==========================================================
# HELPER: EMPTY STATE RESPONSE
# ==========================================================

def _empty_dashboard_response():
    return JSONResponse({
        "metadata": {"total_reviews": 0},
        "kpis": {
            "average_rating": 0,
            "reputation_score": 0
        },
        "visualizations": {
            "ratings": {1: 0, 2: 0, 3: 0, 4: 0, 5: 0},
            "emotions": {"Positive": 0, "Neutral": 0, "Negative": 0},
            "sentiment_trend": []
        }
    })
