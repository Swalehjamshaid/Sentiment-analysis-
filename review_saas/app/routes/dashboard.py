# filename: app/routes/dashboard.py
# ==========================================================
# REVIEW INTELLIGENCE DASHBOARD - FULLY INTEGRATED WITH FRONTEND
# PostgreSQL Optimized + Company Filtering
# ==========================================================

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from datetime import datetime
from typing import List, Optional
import numpy as np
from wordcloud import WordCloud
from collections import Counter
from io import BytesIO
import base64
from sklearn.linear_model import LinearRegression

from app.core.db import get_session
from app.core import models

router = APIRouter(
    prefix="/dashboard",
    tags=["dashboard"],
)

# ---------------------------
# Utilities
# ---------------------------
def encode_image_to_base64(img) -> str:
    buffered = BytesIO()
    img.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode("utf-8")


def calculate_nps(scores: List[int]) -> int:
    if not scores:
        return 0
    promoters = sum(1 for s in scores if s >= 9)
    detractors = sum(1 for s in scores if s <= 6)
    return int((promoters - detractors) / len(scores) * 100)


def calculate_csat(scores: List[int]) -> float:
    if not scores:
        return 0.0
    return round(np.mean(scores) * 20, 2)


# ---------------------------
# 1. Main Summary (KPIs)
# ---------------------------
@router.get("/summary")
async def review_summary(
    session: AsyncSession = Depends(get_session),
    company_id: int = Query(..., description="Company ID"),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
):
    query = select(models.Review.rating, models.Review.created_at).where(
        models.Review.company_id == company_id
    )

    if start_date:
        query = query.where(models.Review.created_at >= start_date)
    if end_date:
        query = query.where(models.Review.created_at <= end_date)

    result = await session.execute(query)
    reviews = result.all()
    ratings = [r.rating for r in reviews if r.rating is not None]

    return JSONResponse(
        content={
            "total_reviews": len(reviews),
            "average_rating": round(np.mean(ratings), 2) if ratings else 0,
            "nps": calculate_nps(ratings),
            "csat": calculate_csat(ratings),
            "start_date": start_date,
            "end_date": end_date,
        }
    )


# ---------------------------
# 2. Rating Trends (for Sentiment Trend Chart)
# ---------------------------
@router.get("/trends")
async def rating_trends(
    session: AsyncSession = Depends(get_session),
    company_id: int = Query(..., description="Company ID"),
    period: str = Query("monthly", enum=["daily", "monthly", "yearly"]),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
):
    if period == "daily":
        date_expr = func.date(models.Review.created_at)
    elif period == "monthly":
        date_expr = func.date_trunc("month", models.Review.created_at)
    else:
        date_expr = func.date_trunc("year", models.Review.created_at)

    query = (
        select(
            date_expr.label("period"),
            func.avg(models.Review.rating).label("avg_rating"),
            func.count(models.Review.id).label("review_count")
        )
        .where(models.Review.company_id == company_id)
        .group_by("period")
        .order_by("period")
    )

    if start_date:
        query = query.where(models.Review.created_at >= start_date)
    if end_date:
        query = query.where(models.Review.created_at <= end_date)

    result = await session.execute(query)
    trends = [
        {
            "period": str(r.period)[:10],   # simplify for frontend
            "avg": round(float(r.avg_rating), 2) if r.avg_rating else 0,
        }
        for r in result.all()
    ]

    return JSONResponse(content={"trends": trends})


# ---------------------------
# 3. Rating Distribution (for Bar Chart)
# ---------------------------
@router.get("/ratings-distribution")
async def ratings_distribution(
    session: AsyncSession = Depends(get_session),
    company_id: int = Query(..., description="Company ID"),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
):
    query = (
        select(
            models.Review.rating,
            func.count(models.Review.id).label("count")
        )
        .where(models.Review.company_id == company_id)
        .group_by(models.Review.rating)
    )

    if start_date:
        query = query.where(models.Review.created_at >= start_date)
    if end_date:
        query = query.where(models.Review.created_at <= end_date)

    result = await session.execute(query)
    dist = {str(r.rating): r.count for r in result.all() if r.rating}

    # Fill missing ratings 1-5
    for i in range(1, 6):
        if str(i) not in dist:
            dist[str(i)] = 0

    return JSONResponse(content={"ratings": dist})


# ---------------------------
# 4. Emotions / Aspect Radar (Simple version from aspects)
# ---------------------------
@router.get("/emotions")
async def emotions_radar(
    session: AsyncSession = Depends(get_session),
    company_id: int = Query(..., description="Company ID"),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
):
    query = select(
        func.avg(models.Review.aspect_rooms).label("rooms"),
        func.avg(models.Review.aspect_staff).label("staff"),
        func.avg(models.Review.aspect_location).label("location"),
        func.avg(models.Review.aspect_service).label("service"),
        func.avg(models.Review.aspect_cleanliness).label("cleanliness"),
        func.avg(models.Review.aspect_food).label("food"),
    ).where(models.Review.company_id == company_id)

    if start_date:
        query = query.where(models.Review.created_at >= start_date)
    if end_date:
        query = query.where(models.Review.created_at <= end_date)

    result = await session.execute(query)
    row = result.first()

    emotions = {
        "Rooms": round(float(row.rooms or 0), 1),
        "Staff": round(float(row.staff or 0), 1),
        "Location": round(float(row.location or 0), 1),
        "Service": round(float(row.service or 0), 1),
        "Cleanliness": round(float(row.cleanliness or 0), 1),
        "Food": round(float(row.food or 0), 1),
    }

    return JSONResponse(content={"emotions": emotions})


# ---------------------------
# 5. Word Cloud → Keyword Badges
# ---------------------------
@router.get("/wordcloud")
async def wordcloud_data(
    session: AsyncSession = Depends(get_session),
    company_id: int = Query(..., description="Company ID"),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    limit: int = Query(20),
):
    query = select(models.Review.text).where(models.Review.company_id == company_id)

    if start_date:
        query = query.where(models.Review.created_at >= start_date)
    if end_date:
        query = query.where(models.Review.created_at <= end_date)

    result = await session.execute(query)
    comments = [r.text for r in result.all() if r.text and r.text.strip()]

    if not comments:
        return JSONResponse(content={"keywords": []})

    # Simple keyword extraction (top words)
    all_text = " ".join(comments).lower()
    words = [w for w in all_text.split() if len(w) > 3]
    word_counts = Counter(words).most_common(limit)

    keywords = [{"text": word, "value": count} for word, count in word_counts]

    return JSONResponse(content={"keywords": keywords})


# ---------------------------
# 6. Forecast (optional - can be called separately)
# ---------------------------
@router.get("/forecast")
async def ratings_forecast(
    session: AsyncSession = Depends(get_session),
    company_id: int = Query(..., description="Company ID"),
    future_periods: int = Query(6),
):
    result = await session.execute(
        select(models.Review.created_at, models.Review.rating)
        .where(models.Review.company_id == company_id)
        .order_by(models.Review.created_at)
    )
    data = result.all()

    if len(data) < 10:
        return JSONResponse(content={"forecast": [], "message": "Not enough data"})

    dates = np.array([r.created_at.timestamp() for r in data]).reshape(-1, 1)
    ratings = np.array([r.rating for r in data])

    model = LinearRegression()
    model.fit(dates, ratings)

    last_ts = dates[-1][0]
    step = (dates[-1][0] - dates[0][0]) / len(dates) if len(dates) > 1 else 86400

    future_ts = np.array([last_ts + step * (i + 1) for i in range(future_periods)]).reshape(-1, 1)
    predicted = model.predict(future_ts)

    forecast = [
        {"date": datetime.fromtimestamp(ts).strftime("%Y-%m-%d"), "predicted_rating": round(float(p), 2)}
        for ts, p in zip(future_ts.flatten(), predicted)
    ]

    return JSONResponse(content={"forecast": forecast})
