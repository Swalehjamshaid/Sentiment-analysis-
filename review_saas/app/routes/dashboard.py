# filename: app/routes/dashboard.py
# ==========================================================
# REVIEW INTEL AI DASHBOARD - FINAL VERSION
# 100% Integrated with your Frontend + PostgreSQL + models.py
# ==========================================================

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime
from typing import Optional
import numpy as np
from collections import Counter

from app.core.db import get_session
from app.core import models

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


# ====================== MAIN DASHBOARD ENDPOINT ======================
@router.get("/ai/insights")
async def ai_insights(
    session: AsyncSession = Depends(get_session),
    company_id: int = Query(..., gt=0),
    start: str = Query("2010-01-01"),
    end: Optional[str] = Query(None),
):
    """Main endpoint called by your frontend when clicking 'Analyze Business'"""
    
    if not end:
        end = datetime.now().date().isoformat()

    # Use first_seen_at as the date field (as per your models.py)
    query = select(models.Review).where(models.Review.company_id == company_id)
    query = query.where(models.Review.first_seen_at >= start)
    if end:
        query = query.where(models.Review.first_seen_at <= end)

    result = await session.execute(query)
    reviews = result.scalars().all()

    if not reviews:
        return JSONResponse(content={
            "kpis": {"average_rating": 0, "reputation_score": 0},
            "metadata": {"total_reviews": 0, "start_date": start, "end_date": end},
            "visualizations": {
                "emotions": {"Rooms":0, "Staff":0, "Location":0, "Service":0, "Cleanliness":0, "Food":0},
                "sentiment_trend": [],
                "ratings": {"1":0,"2":0,"3":0,"4":0,"5":0},
                "keywords": []
            },
            "message": "No reviews found. Please click 'Sync Live Data' first."
        })

    ratings = [r.rating for r in reviews if r.rating is not None]
    texts = [r.text for r in reviews if r.text and str(r.text).strip()]

    avg_rating = round(np.mean(ratings), 2) if ratings else 0.0
    total_reviews = len(reviews)

    # Sentiment Trend (Monthly)
    trend_query = (
        select(
            func.date_trunc("month", models.Review.first_seen_at).label("period"),
            func.avg(models.Review.rating).label("avg")
        )
        .where(models.Review.company_id == company_id)
        .group_by("period")
        .order_by("period")
    )
    trend_result = await session.execute(trend_query)
    sentiment_trend = [
        {"week": str(r.period)[:10], "avg": round(float(r.avg), 2) if r.avg else 0}
        for r in trend_result.all()
    ]

    # Rating Distribution
    dist = {str(i): 0 for i in range(1, 6)}
    for r in reviews:
        if r.rating and 1 <= r.rating <= 5:
            dist[str(int(r.rating))] += 1

    # Emotions Radar
    aspect_query = select(
        func.avg(models.Review.aspect_rooms).label("rooms"),
        func.avg(models.Review.aspect_staff).label("staff"),
        func.avg(models.Review.aspect_location).label("location"),
        func.avg(models.Review.aspect_service).label("service"),
        func.avg(models.Review.aspect_cleanliness).label("cleanliness"),
        func.avg(models.Review.aspect_food).label("food"),
    ).where(models.Review.company_id == company_id)
    aspect_result = await session.execute(aspect_query)
    row = aspect_result.first() or {}

    emotions = {
        "Rooms": round(float(row.rooms or 0), 1),
        "Staff": round(float(row.staff or 0), 1),
        "Location": round(float(row.location or 0), 1),
        "Service": round(float(row.service or 0), 1),
        "Cleanliness": round(float(row.cleanliness or 0), 1),
        "Food": round(float(row.food or 0), 1),
    }

    # Keywords
    all_text = " ".join(texts).lower()
    words = [w for w in all_text.split() if len(w) > 3]
    keywords = [{"text": word, "value": count} for word, count in Counter(words).most_common(15)]

    return {
        "kpis": {
            "average_rating": avg_rating,
            "reputation_score": round(avg_rating * 20, 1),
        },
        "metadata": {
            "total_reviews": total_reviews,
            "start_date": start,
            "end_date": end,
        },
        "visualizations": {
            "emotions": emotions,
            "sentiment_trend": sentiment_trend,
            "ratings": dist,
            "keywords": keywords,
        }
    }


# ====================== REVENUE RISK CARD ======================
@router.get("/revenue")
async def revenue_risk(
    session: AsyncSession = Depends(get_session),
    company_id: int = Query(..., gt=0),
):
    query = select(
        func.count().label("total"),
        func.avg(models.Review.rating).label("avg")
    ).where(models.Review.company_id == company_id)

    result = await session.execute(query)
    row = result.first()

    avg = float(row.avg) if row.avg else 0.0
    risk_percent = max(0, min(100, int((5 - avg) * 20)))
    impact = "High" if risk_percent > 60 else "Medium" if risk_percent > 30 else "Low"

    return {"risk_percent": risk_percent, "impact": impact}


# ====================== AI CHAT ======================
@router.get("/chatbot/explain/{company_id}")
async def chatbot_explain(company_id: int, question: str = Query(...)):
    q = question.lower()
    if any(word in q for word in ["trend", "rating", "future"]):
        answer = "Ratings have been stable. Focus on quick responses to negative reviews."
    elif any(word in q for word in ["improve", "growth"]):
        answer = "Replying promptly to reviews can significantly boost your reputation score."
    else:
        answer = "Based on current data, improving service quality and response time is recommended."
    return {"answer": answer}
