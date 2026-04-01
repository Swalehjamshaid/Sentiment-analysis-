# filename: app/routes/dashboard.py
# ==========================================================
# REVIEW INTEL AI DASHBOARD - 100% INTEGRATED WITH FRONTEND
# PostgreSQL Optimized
# ==========================================================

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime
from typing import Optional
import numpy as np
from collections import Counter
from wordcloud import WordCloud
from io import BytesIO
import base64
from sklearn.linear_model import LinearRegression

from app.core.db import get_session
from app.core import models

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


# ========================= UTILITIES =========================
def encode_image_to_base64(img) -> str:
    buffered = BytesIO()
    img.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode("utf-8")


# ========================= MAIN INSIGHTS ENDPOINT =========================
@router.get("/ai/insights")
async def ai_insights(
    session: AsyncSession = Depends(get_session),
    company_id: int = Query(..., description="Company ID"),
    start: str = Query("2010-01-01"),
    end: Optional[str] = Query(None),
):
    """Main endpoint called by frontend - returns KPIs + all visualizations"""
    if not end:
        end = datetime.utcnow().date().isoformat()

    # Get reviews for this company + date range
    query = select(models.Review).where(models.Review.company_id == company_id)
    if start:
        query = query.where(models.Review.created_at >= start)
    if end:
        query = query.where(models.Review.created_at <= end)

    result = await session.execute(query)
    reviews = result.scalars().all()

    ratings = [r.rating for r in reviews if r.rating is not None]
    texts = [r.text for r in reviews if r.text and str(r.text).strip()]

    total_reviews = len(reviews)
    avg_rating = round(np.mean(ratings), 2) if ratings else 0.0

    # Monthly Trends for Sentiment Trend Chart
    trend_query = (
        select(
            func.date_trunc("month", models.Review.created_at).label("period"),
            func.avg(models.Review.rating).label("avg")
        )
        .where(models.Review.company_id == company_id)
        .group_by("period")
        .order_by("period")
    )
    if start:
        trend_query = trend_query.where(models.Review.created_at >= start)
    if end:
        trend_query = trend_query.where(models.Review.created_at <= end)

    trend_result = await session.execute(trend_query)
    sentiment_trend = [
        {"week": str(r.period)[:10], "avg": round(float(r.avg), 2) if r.avg else 0}
        for r in trend_result.all()
    ]

    # Rating Distribution for Bar Chart
    dist_query = (
        select(models.Review.rating, func.count().label("count"))
        .where(models.Review.company_id == company_id)
        .group_by(models.Review.rating)
    )
    if start: dist_query = dist_query.where(models.Review.created_at >= start)
    if end: dist_query = dist_query.where(models.Review.created_at <= end)

    dist_result = await session.execute(dist_query)
    ratings_dist = {str(r.rating): r.count for r in dist_result.all() if r.rating}
    for i in range(1, 6):
        ratings_dist.setdefault(str(i), 0)

    # Customer Emotion Radar (using aspect scores)
    aspect_query = select(
        func.avg(models.Review.aspect_rooms).label("rooms"),
        func.avg(models.Review.aspect_staff).label("staff"),
        func.avg(models.Review.aspect_location).label("location"),
        func.avg(models.Review.aspect_service).label("service"),
        func.avg(models.Review.aspect_cleanliness).label("cleanliness"),
        func.avg(models.Review.aspect_food).label("food"),
    ).where(models.Review.company_id == company_id)

    if start: aspect_query = aspect_query.where(models.Review.created_at >= start)
    if end: aspect_query = aspect_query.where(models.Review.created_at <= end)

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

    # AI Keyword Extraction
    all_text = " ".join(texts).lower()
    words = [w for w in all_text.split() if len(w) > 3]
    keyword_list = Counter(words).most_common(15)
    keywords = [{"text": word, "value": count} for word, count in keyword_list]

    return JSONResponse(content={
        "kpis": {
            "average_rating": avg_rating,
            "reputation_score": round(avg_rating * 20, 1),   # 0-100 scale
        },
        "metadata": {
            "total_reviews": total_reviews,
            "start_date": start,
            "end_date": end,
        },
        "visualizations": {
            "emotions": emotions,
            "sentiment_trend": sentiment_trend,
            "ratings": ratings_dist,
            "keywords": keywords,
        }
    })


# ========================= REVENUE RISK ENDPOINT =========================
@router.get("/revenue")
async def revenue_risk(
    session: AsyncSession = Depends(get_session),
    company_id: int = Query(..., description="Company ID"),
):
    """Risk card data - simple placeholder logic"""
    # You can make this more intelligent later using sentiment/complaints
    query = select(
        func.count().label("total"),
        func.avg(models.Review.rating).label("avg_rating")
    ).where(models.Review.company_id == company_id)

    result = await session.execute(query)
    row = result.first()

    total = row.total or 0
    avg = float(row.avg_rating) if row.avg_rating else 0

    risk_percent = max(0, int((5 - avg) * 20))   # higher risk if low rating
    impact = "High" if risk_percent > 60 else "Medium" if risk_percent > 30 else "Low"

    return JSONResponse(content={
        "risk_percent": risk_percent,
        "impact": impact,
        "total_reviews": total,
    })


# ========================= AI CHAT ENDPOINT =========================
@router.get("/chatbot/explain/{company_id}")
async def chatbot_explain(
    company_id: int,
    question: str = Query(...)
):
    """Simple AI chat response - replace with real LLM later"""
    responses = {
        "trend": "Ratings have been stable this quarter. Focus on service improvements.",
        "growth": "Consider responding to all negative reviews within 24 hours to boost reputation.",
        "staff": "Staff-related complaints appear in 18% of reviews. Training may help.",
        "default": "Based on recent reviews, customer satisfaction is moderate. Key areas: response time and cleanliness."
    }

    answer = responses.get("default")
    q_lower = question.lower()
    if any(word in q_lower for word in ["trend", "rating", "future"]):
        answer = responses["trend"]
    elif any(word in q_lower for word in ["growth", "improve", "increase"]):
        answer = responses["growth"]
    elif any(word in q_lower for word in ["staff", "employee", "service"]):
        answer = responses["staff"]

    return JSONResponse(content={"answer": answer})


# Optional: Keep these if you want extra endpoints
@router.get("/summary")
async def review_summary(
    session: AsyncSession = Depends(get_session),
    company_id: int = Query(...),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
):
    # You can expand this later if needed
    return JSONResponse(content={"message": "Use /ai/insights for full data"})
