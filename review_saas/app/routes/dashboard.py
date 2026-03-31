# filename: app/routes/dashboard.py

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from datetime import datetime

from app.core.db import get_session
from app.core.models import Review

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])


def safe(val):
    try:
        return round(float(val), 2)
    except:
        return 0


# =========================================================
# MAIN DASHBOARD (FIXED DATA FILTER)
# =========================================================
@router.get("/ai/insights")
async def get_ai_insights(
    company_id: int,
    start: str,
    end: str,
    db: AsyncSession = Depends(get_session)
):

    # ✅ SAFE DATE PARSE
    try:
        start_date = datetime.fromisoformat(start)
        end_date = datetime.fromisoformat(end)
    except:
        start_date = None
        end_date = None

    # =====================================================
    # 🔥 FIX: HANDLE NULL DATES + EXISTING DATA
    # =====================================================
    filters = [Review.company_id == company_id]

    if start_date and end_date:
        filters.append(
            or_(
                Review.google_review_time == None,  # include nulls
                Review.google_review_time.between(start_date, end_date)
            )
        )

    # -------------------------
    # TOTAL REVIEWS
    # -------------------------
    total_reviews = await db.scalar(
        select(func.count(Review.id)).where(*filters)
    ) or 0

    # -------------------------
    # AVG RATING
    # -------------------------
    avg_rating = await db.scalar(
        select(func.avg(Review.rating)).where(*filters)
    ) or 0

    # -------------------------
    # SENTIMENT
    # -------------------------
    sentiment = await db.scalar(
        select(func.avg(Review.sentiment_score)).where(*filters)
    ) or 0

    # -------------------------
    # RATING DISTRIBUTION
    # -------------------------
    rating_rows = await db.execute(
        select(Review.rating, func.count())
        .where(*filters)
        .group_by(Review.rating)
    )

    ratings = {1:0,2:0,3:0,4:0,5:0}
    for r, c in rating_rows:
        if r in ratings:
            ratings[r] = c

    # -------------------------
    # TREND (IGNORE NULL DATES)
    # -------------------------
    trend_rows = await db.execute(
        select(
            func.date_trunc('month', Review.google_review_time),
            func.avg(Review.sentiment_score)
        )
        .where(
            Review.company_id == company_id,
            Review.google_review_time != None
        )
        .group_by(func.date_trunc('month', Review.google_review_time))
        .order_by(func.date_trunc('month', Review.google_review_time))
    )

    sentiment_trend = [
        {
            "month": str(row[0].date()),
            "avg": safe(row[1])
        }
        for row in trend_rows
    ]

    # -------------------------
    # EMOTIONS (SMART)
    # -------------------------
    emotions = {
        "Happy": safe(sentiment * 10),
        "Neutral": 50,
        "Angry": safe(100 - sentiment * 10)
    }

    return {
        "metadata": {
            "total_reviews": total_reviews
        },
        "kpis": {
            "average_rating": safe(avg_rating),
            "reputation_score": safe(sentiment)
        },
        "visualizations": {
            "ratings": ratings,
            "sentiment_trend": sentiment_trend,
            "emotions": emotions
        }
    }


# =========================================================
# REVENUE API (UNCHANGED BUT SAFE)
# =========================================================
@router.get("/revenue")
async def revenue(
    company_id: int,
    db: AsyncSession = Depends(get_session)
):
    avg = await db.scalar(
        select(func.avg(Review.rating))
        .where(Review.company_id == company_id)
    ) or 0

    avg = safe(avg)

    if avg >= 4.5:
        return {"risk_percent": 5, "impact": "Low"}
    elif avg >= 4.0:
        return {"risk_percent": 15, "impact": "Moderate"}
    elif avg >= 3.0:
        return {"risk_percent": 35, "impact": "High"}
    elif avg > 0:
        return {"risk_percent": 60, "impact": "Critical"}
    else:
        return {"risk_percent": 0, "impact": "No Data"}
