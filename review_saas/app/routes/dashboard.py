# filename: app/routes/dashboard.py

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime
from collections import Counter, defaultdict
import random

from app.core.db import get_session
from app.core import models

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


# =========================================================
# AI INSIGHTS (MAIN ENDPOINT - USED BY FRONTEND)
# =========================================================
@router.get("/ai/insights")
async def get_ai_insights(
    company_id: int,
    start: str,
    end: str,
    db: AsyncSession = Depends(get_session),
):
    query = select(models.Review).where(models.Review.company_id == company_id)

    result = await db.execute(query)
    reviews = result.scalars().all()

    if not reviews:
        return JSONResponse(content={
            "metadata": {"total_reviews": 0},
            "kpis": {},
            "visualizations": {}
        })

    # ---------------- KPIs ----------------
    total_reviews = len(reviews)
    avg_rating = round(sum(r.rating for r in reviews) / total_reviews, 2)

    # Reputation score (simple logic)
    reputation = round((avg_rating / 5) * 100, 2)

    # ---------------- Ratings Distribution ----------------
    rating_counts = Counter([r.rating for r in reviews])
    ratings = {
        "1": rating_counts.get(1, 0),
        "2": rating_counts.get(2, 0),
        "3": rating_counts.get(3, 0),
        "4": rating_counts.get(4, 0),
        "5": rating_counts.get(5, 0),
    }

    # ---------------- Sentiment Trend ----------------
    trend_map = defaultdict(list)
    for r in reviews:
        week = r.created_at.strftime("%Y-%W")
        trend_map[week].append(r.rating)

    sentiment_trend = [
        {"week": k, "avg": round(sum(v)/len(v), 2)}
        for k, v in sorted(trend_map.items())
    ]

    # ---------------- Emotions (Mock AI logic) ----------------
    emotions = {
        "Happy": random.randint(20, 80),
        "Angry": random.randint(5, 30),
        "Neutral": random.randint(10, 50),
        "Excited": random.randint(10, 60),
        "Frustrated": random.randint(5, 40),
    }

    # ---------------- Keywords ----------------
    words = []
    for r in reviews:
        if r.comment:
            words.extend(r.comment.lower().split())

    common_words = Counter(words).most_common(20)
    keywords = [{"text": w, "value": c} for w, c in common_words]

    return JSONResponse(content={
        "metadata": {
            "total_reviews": total_reviews
        },
        "kpis": {
            "average_rating": avg_rating,
            "reputation_score": reputation
        },
        "visualizations": {
            "ratings": ratings,
            "sentiment_trend": sentiment_trend,
            "emotions": emotions,
            "keywords": keywords
        }
    })


# =========================================================
# REVENUE RISK
# =========================================================
@router.get("/revenue")
async def revenue_risk(
    company_id: int,
    db: AsyncSession = Depends(get_session)
):
    result = await db.execute(
        select(models.Review.rating).where(models.Review.company_id == company_id)
    )
    ratings = [r[0] for r in result.all()]

    if not ratings:
        return {"risk_percent": 0, "impact": "Low"}

    avg = sum(ratings) / len(ratings)

    risk_percent = int((5 - avg) / 5 * 100)

    if risk_percent > 60:
        impact = "High"
    elif risk_percent > 30:
        impact = "Medium"
    else:
        impact = "Low"

    return {
        "risk_percent": risk_percent,
        "impact": impact
    }


# =========================================================
# AI CHATBOT
# =========================================================
@router.get("/chatbot/explain/{company_id}")
async def chatbot_explain(
    company_id: int,
    question: str,
    db: AsyncSession = Depends(get_session)
):
    result = await db.execute(
        select(models.Review.rating).where(models.Review.company_id == company_id)
    )
    ratings = [r[0] for r in result.all()]

    if not ratings:
        return {"answer": "No data available for this business."}

    avg = round(sum(ratings) / len(ratings), 2)

    # Simple AI logic
    if avg >= 4:
        insight = "Strong performance with high customer satisfaction."
    elif avg >= 3:
        insight = "Moderate performance. Improvement needed."
    else:
        insight = "Critical risk. Immediate action required."

    return {
        "answer": f"Average rating is {avg}. {insight}"
    }


# =========================================================
# PDF REPORT (DUMMY LINK)
# =========================================================
@router.get("/executive-report/pdf/{company_id}")
async def download_report(company_id: int):
    return JSONResponse(content={
        "message": "Report generation not implemented yet",
        "company_id": company_id
    })
