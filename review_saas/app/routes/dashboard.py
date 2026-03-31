# filename: app/routes/dashboard.py

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime

from app.core.db import get_session   # ✅ FIXED
from app.core.models import Review, Company

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])


# ---------------------------------------------------------
# 1. AI INSIGHTS ENDPOINT (MAIN FRONTEND DRIVER)
# ---------------------------------------------------------
@router.get("/ai/insights")
async def get_ai_insights(
    company_id: int = Query(...),
    start: str = Query(...),
    end: str = Query(...),
    db: AsyncSession = Depends(get_session)
):
    try:
        start_date = datetime.fromisoformat(start)
        end_date = datetime.fromisoformat(end)
    except:
        return {"error": "Invalid date format"}

    # ----------------------------
    # TOTAL REVIEWS
    # ----------------------------
    total_reviews_query = await db.execute(
        select(func.count(Review.id)).where(
            Review.company_id == company_id,
            Review.google_review_time >= start_date,
            Review.google_review_time <= end_date
        )
    )
    total_reviews = total_reviews_query.scalar() or 0

    # ----------------------------
    # AVG RATING
    # ----------------------------
    avg_rating_query = await db.execute(
        select(func.avg(Review.rating)).where(
            Review.company_id == company_id
        )
    )
    avg_rating = round(avg_rating_query.scalar() or 0, 2)

    # ----------------------------
    # SENTIMENT SCORE
    # ----------------------------
    sentiment_query = await db.execute(
        select(func.avg(Review.sentiment_score)).where(
            Review.company_id == company_id
        )
    )
    sentiment_score = round(sentiment_query.scalar() or 0, 2)

    # ----------------------------
    # RATING DISTRIBUTION
    # ----------------------------
    ratings_query = await db.execute(
        select(Review.rating, func.count(Review.id))
        .where(Review.company_id == company_id)
        .group_by(Review.rating)
    )

    ratings_data = {1:0,2:0,3:0,4:0,5:0}
    for r, count in ratings_query.all():
        if r in ratings_data:
            ratings_data[r] = count

    # ----------------------------
    # SENTIMENT TREND (MONTHLY)
    # ----------------------------
    trend_query = await db.execute(
        select(
            func.date_trunc('month', Review.google_review_time),
            func.avg(Review.sentiment_score)
        )
        .where(Review.company_id == company_id)
        .group_by(func.date_trunc('month', Review.google_review_time))
        .order_by(func.date_trunc('month', Review.google_review_time))
    )

    sentiment_trend = [
        {
            "month": str(row[0].date()),
            "avg": round(row[1] or 0, 2)
        }
        for row in trend_query.all()
    ]

    # ----------------------------
    # EMOTION MOCK (can upgrade later)
    # ----------------------------
    emotions = {
        "happy": round(sentiment_score * 10, 2),
        "neutral": 50,
        "angry": 100 - (sentiment_score * 10)
    }

    return {
        "metadata": {
            "total_reviews": total_reviews
        },
        "kpis": {
            "average_rating": avg_rating,
            "reputation_score": sentiment_score
        },
        "visualizations": {
            "ratings": ratings_data,
            "sentiment_trend": sentiment_trend,
            "emotions": emotions
        }
    }


# ---------------------------------------------------------
# 2. REVENUE RISK ENDPOINT
# ---------------------------------------------------------
@router.get("/revenue")
async def revenue_risk(
    company_id: int,
    db: AsyncSession = Depends(get_session)
):
    # Avg rating
    avg_rating_query = await db.execute(
        select(func.avg(Review.rating)).where(
            Review.company_id == company_id
        )
    )
    avg_rating = avg_rating_query.scalar() or 0

    # Risk Logic
    if avg_rating >= 4.5:
        risk = 5
        impact = "Low"
    elif avg_rating >= 4.0:
        risk = 15
        impact = "Moderate"
    elif avg_rating >= 3.0:
        risk = 35
        impact = "High"
    else:
        risk = 60
        impact = "Critical"

    return {
        "risk_percent": risk,
        "impact": impact
    }
