# filename: app/routes/dashboard.py

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime

from app.core.db import get_session
from app.core.models import Review

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])


# =========================================================
# HELPER: SAFE FLOAT
# =========================================================
def safe_round(value, digits=2):
    try:
        return round(float(value), digits)
    except:
        return 0


# =========================================================
# MAIN AI INSIGHTS ENDPOINT
# (USED BY FRONTEND triggerAllLoads())
# =========================================================
@router.get("/ai/insights")
async def get_ai_insights(
    company_id: int = Query(...),
    start: str = Query(...),
    end: str = Query(...),
    db: AsyncSession = Depends(get_session)
):
    # -------------------------
    # DATE PARSING SAFE
    # -------------------------
    try:
        start_date = datetime.fromisoformat(start)
        end_date = datetime.fromisoformat(end)
    except:
        return {
            "metadata": {"total_reviews": 0},
            "kpis": {},
            "visualizations": {}
        }

    # -------------------------
    # BASE QUERY FILTER
    # -------------------------
    base_filter = [
        Review.company_id == company_id,
        Review.google_review_time >= start_date,
        Review.google_review_time <= end_date
    ]

    # -------------------------
    # TOTAL REVIEWS
    # -------------------------
    total_reviews = await db.scalar(
        select(func.count(Review.id)).where(*base_filter)
    ) or 0

    # -------------------------
    # AVG RATING
    # -------------------------
    avg_rating = await db.scalar(
        select(func.avg(Review.rating)).where(*base_filter)
    ) or 0

    avg_rating = safe_round(avg_rating)

    # -------------------------
    # SENTIMENT SCORE
    # -------------------------
    sentiment_score = await db.scalar(
        select(func.avg(Review.sentiment_score)).where(*base_filter)
    ) or 0

    sentiment_score = safe_round(sentiment_score)

    # -------------------------
    # RATING DISTRIBUTION
    # -------------------------
    rating_rows = await db.execute(
        select(Review.rating, func.count(Review.id))
        .where(*base_filter)
        .group_by(Review.rating)
    )

    ratings = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    for r, count in rating_rows.all():
        if r in ratings:
            ratings[r] = count

    # -------------------------
    # SENTIMENT TREND (MONTHLY)
    # -------------------------
    trend_rows = await db.execute(
        select(
            func.date_trunc('month', Review.google_review_time).label("month"),
            func.avg(Review.sentiment_score)
        )
        .where(*base_filter)
        .group_by("month")
        .order_by("month")
    )

    sentiment_trend = []
    for row in trend_rows.all():
        sentiment_trend.append({
            "month": str(row.month.date()) if row.month else "",
            "avg": safe_round(row[1])
        })

    # -------------------------
    # EMOTION ENGINE (SMART)
    # -------------------------
    emotions = {
        "Happy": safe_round(sentiment_score * 10),
        "Neutral": safe_round(50 - abs(sentiment_score * 5)),
        "Angry": safe_round(100 - (sentiment_score * 10))
    }

    # -------------------------
    # FINAL RESPONSE (STRICT FRONTEND FORMAT)
    # -------------------------
    return {
        "metadata": {
            "total_reviews": total_reviews
        },
        "kpis": {
            "average_rating": avg_rating,
            "reputation_score": sentiment_score
        },
        "visualizations": {
            "ratings": ratings,
            "sentiment_trend": sentiment_trend,
            "emotions": emotions
        }
    }


# =========================================================
# REVENUE RISK API
# (USED BY FRONTEND /api/dashboard/revenue)
# =========================================================
@router.get("/revenue")
async def revenue_risk(
    company_id: int,
    db: AsyncSession = Depends(get_session)
):
    avg_rating = await db.scalar(
        select(func.avg(Review.rating)).where(
            Review.company_id == company_id
        )
    ) or 0

    avg_rating = safe_round(avg_rating)

    # -------------------------
    # BUSINESS RISK LOGIC
    # -------------------------
    if avg_rating >= 4.5:
        risk_percent = 5
        impact = "Low"
    elif avg_rating >= 4.0:
        risk_percent = 15
        impact = "Moderate"
    elif avg_rating >= 3.0:
        risk_percent = 35
        impact = "High"
    elif avg_rating > 0:
        risk_percent = 60
        impact = "Critical"
    else:
        risk_percent = 0
        impact = "No Data"

    return {
        "risk_percent": risk_percent,
        "impact": impact
    }
