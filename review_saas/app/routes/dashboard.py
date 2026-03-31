# filename: app/routes/dashboard.py

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime
from collections import defaultdict

from app.core.db import get_session
from app.core.models import Review, Company

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])


# =====================================================
# MAIN AI DASHBOARD ENDPOINT (FRONTEND CONNECTED)
# =====================================================
@router.get("/ai/insights")
async def get_dashboard_insights(
    company_id: int = Query(...),
    start: str = Query(...),
    end: str = Query(...),
    db: AsyncSession = Depends(get_session)
):
    try:
        # Parse dates safely
        try:
            start_date = datetime.fromisoformat(start)
            end_date = datetime.fromisoformat(end)
        except:
            start_date = datetime(2024, 1, 1)
            end_date = datetime.utcnow()

        # Fetch reviews
        result = await db.execute(
            select(Review).where(
                Review.company_id == company_id,
                Review.google_review_time != None,
                Review.google_review_time >= start_date,
                Review.google_review_time <= end_date
            )
        )

        reviews = result.scalars().all()

        total_reviews = len(reviews)

        # =================================================
        # KPI CALCULATIONS
        # =================================================
        avg_rating = 0
        avg_sentiment = 0

        if total_reviews > 0:
            avg_rating = round(
                sum([(r.rating or 0) for r in reviews]) / total_reviews, 2
            )

            avg_sentiment = round(
                sum([(r.sentiment_score or 0) for r in reviews]) / total_reviews, 2
            )

        # =================================================
        # RATING DISTRIBUTION (FOR BAR CHART)
        # =================================================
        ratings = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}

        for r in reviews:
            if r.rating and r.rating in ratings:
                ratings[r.rating] += 1

        # =================================================
        # SENTIMENT TREND (LINE CHART)
        # =================================================
        trend_map = defaultdict(list)

        for r in reviews:
            if r.google_review_time:
                key = r.google_review_time.strftime("%Y-%m")
                trend_map[key].append(r.sentiment_score or 0)

        sentiment_trend = []

        for k in sorted(trend_map.keys()):
            values = trend_map[k]
            sentiment_trend.append({
                "month": k,
                "avg": round(sum(values) / len(values), 2)
            })

        # =================================================
        # EMOTION RADAR (RADAR CHART)
        # =================================================
        emotions = {
            "happy": 0,
            "neutral": 0,
            "angry": 0
        }

        for r in reviews:
            score = r.sentiment_score or 0
            if score > 0.5:
                emotions["happy"] += 1
            elif score < -0.2:
                emotions["angry"] += 1
            else:
                emotions["neutral"] += 1

        # =================================================
        # FINAL RESPONSE (FRONTEND EXPECTS THIS STRUCTURE)
        # =================================================
        return {
            "metadata": {
                "total_reviews": total_reviews
            },
            "kpis": {
                "average_rating": avg_rating,
                "reputation_score": avg_sentiment
            },
            "visualizations": {
                "ratings": ratings,
                "sentiment_trend": sentiment_trend,
                "emotions": emotions
            }
        }

    except Exception as e:
        return {
            "metadata": {"total_reviews": 0},
            "kpis": {
                "average_rating": 0,
                "reputation_score": 0
            },
            "visualizations": {
                "ratings": {1:0,2:0,3:0,4:0,5:0},
                "sentiment_trend": [],
                "emotions": {"happy":0,"neutral":0,"angry":0}
            },
            "error": str(e)
        }


# =====================================================
# REVENUE RISK ENDPOINT
# =====================================================
@router.get("/revenue")
async def get_revenue_risk(
    company_id: int,
    db: AsyncSession = Depends(get_session)
):
    try:
        result = await db.execute(
            select(func.avg(Review.rating)).where(
                Review.company_id == company_id
            )
        )

        avg_rating = result.scalar() or 0

        # Simple business logic
        if avg_rating >= 4:
            risk = 10
            impact = "Low"
        elif avg_rating >= 3:
            risk = 40
            impact = "Medium"
        else:
            risk = 80
            impact = "High"

        return {
            "risk_percent": int(risk),
            "impact": impact
        }

    except Exception as e:
        return {
            "risk_percent": 0,
            "impact": "N/A",
            "error": str(e)
        }
