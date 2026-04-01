# filename: app/routes/dashboard.py

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime
from collections import defaultdict

from app.core.db import get_session
from app.core import models

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])


# ==========================================================
# HELPER: SAFE SERIALIZER
# ==========================================================

def safe_float(value):
    try:
        return float(value)
    except:
        return 0


# ==========================================================
# MAIN INSIGHTS ENDPOINT (MATCHES FRONTEND)
# ==========================================================

@router.get("/ai/insights")
async def get_dashboard_insights(
    company_id: int = Query(...),
    start: str = Query(...),
    end: str = Query(...),
    db: AsyncSession = Depends(get_session)
):
    try:
        start_date = datetime.fromisoformat(start)
        end_date = datetime.fromisoformat(end)

        # --------------------------------------------------
        # TOTAL REVIEWS (FIXED 🔥)
        # --------------------------------------------------
        total_query = await db.execute(
            select(func.count(models.Review.id)).where(
                models.Review.company_id == company_id,
                models.Review.created_at >= start_date,
                models.Review.created_at <= end_date
            )
        )
        total_reviews = total_query.scalar() or 0

        # --------------------------------------------------
        # AVG RATING
        # --------------------------------------------------
        avg_query = await db.execute(
            select(func.avg(models.Review.rating)).where(
                models.Review.company_id == company_id
            )
        )
        avg_rating = round(safe_float(avg_query.scalar()), 2)

        # --------------------------------------------------
        # RATING DISTRIBUTION
        # --------------------------------------------------
        rating_query = await db.execute(
            select(models.Review.rating, func.count()).where(
                models.Review.company_id == company_id
            ).group_by(models.Review.rating)
        )

        ratings = {i: 0 for i in range(1, 6)}
        for r, count in rating_query.all():
            if r:
                ratings[int(r)] = count

        # --------------------------------------------------
        # SENTIMENT TREND (WEEKLY)
        # --------------------------------------------------
        trend_query = await db.execute(
            select(
                func.date_trunc('week', models.Review.created_at),
                func.avg(models.Review.rating)
            ).where(
                models.Review.company_id == company_id
            ).group_by(
                func.date_trunc('week', models.Review.created_at)
            ).order_by(
                func.date_trunc('week', models.Review.created_at)
            )
        )

        sentiment_trend = [
            {
                "week": str(row[0].date()),
                "avg": round(safe_float(row[1]), 2)
            }
            for row in trend_query.all()
        ]

        # --------------------------------------------------
        # SIMPLE EMOTION MOCK (CAN UPGRADE LATER)
        # --------------------------------------------------
        emotions = {
            "Happy": round(avg_rating * 20, 2),
            "Neutral": 50 - avg_rating * 5,
            "Angry": max(0, 50 - avg_rating * 10),
            "Excited": avg_rating * 15,
            "Frustrated": max(0, 40 - avg_rating * 8)
        }

        # --------------------------------------------------
        # KEYWORDS (SIMPLE WORD COUNT)
        # --------------------------------------------------
        text_query = await db.execute(
            select(models.Review.content).where(
                models.Review.company_id == company_id
            )
        )

        word_count = defaultdict(int)

        for row in text_query.all():
            if row[0]:
                for word in row[0].lower().split():
                    if len(word) > 4:
                        word_count[word] += 1

        keywords = sorted(
            [{"text": k, "value": v} for k, v in word_count.items()],
            key=lambda x: x["value"],
            reverse=True
        )[:15]

        # --------------------------------------------------
        # RESPONSE (MATCHES FRONTEND EXACTLY)
        # --------------------------------------------------
        return {
            "metadata": {
                "total_reviews": total_reviews
            },
            "kpis": {
                "average_rating": avg_rating,
                "reputation_score": avg_rating * 20
            },
            "visualizations": {
                "ratings": ratings,
                "sentiment_trend": sentiment_trend,
                "emotions": emotions,
                "keywords": keywords
            }
        }

    except Exception as e:
        return {"error": str(e)}


# ==========================================================
# REVENUE RISK
# ==========================================================

@router.get("/revenue")
async def revenue_risk(
    company_id: int,
    db: AsyncSession = Depends(get_session)
):
    avg_query = await db.execute(
        select(func.avg(models.Review.rating)).where(
            models.Review.company_id == company_id
        )
    )
    avg_rating = safe_float(avg_query.scalar())

    risk_percent = max(0, 100 - (avg_rating * 20))

    return {
        "risk_percent": round(risk_percent, 2),
        "impact": "High" if risk_percent > 60 else "Medium" if risk_percent > 30 else "Low"
    }


# ==========================================================
# CHATBOT
# ==========================================================

@router.get("/chatbot/explain/{company_id}")
async def chatbot(company_id: int, question: str):
    return {
        "answer": f"AI Insight: Based on reviews, focus on improving customer satisfaction and response time."
    }


# ==========================================================
# PDF REPORT (TEMP)
# ==========================================================

@router.get("/executive-report/pdf/{company_id}")
async def download_report(company_id: int):
    return {"message": f"PDF generation for company {company_id} coming soon"}
