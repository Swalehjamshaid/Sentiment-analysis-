# filename: app/routes/dashboard.py
# ==========================================================
# REVIEW INTELLIGENCE DASHBOARD - FRONTEND INTEGRATED
# ==========================================================

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime
from collections import defaultdict
from typing import List
import numpy as np
from wordcloud import WordCloud
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
    """Encode PIL/WordCloud image to base64 for frontend display"""
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
        return 0
    return round(np.mean(scores) * 20, 2)  # Convert 1-5 scale to 0-100%


# ---------------------------
# Review Summary
# ---------------------------
@router.get("/summary")
async def review_summary(
    session: AsyncSession = Depends(get_session),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
):
    query = select(models.Review.rating, models.Review.created_at)
    if start_date:
        query = query.where(models.Review.created_at >= start_date)
    if end_date:
        query = query.where(models.Review.created_at <= end_date)

    result = await session.execute(query)
    reviews = result.all()
    ratings = [r.rating for r in reviews]

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
# Rating Trends
# ---------------------------
@router.get("/trends")
async def rating_trends(
    session: AsyncSession = Depends(get_session),
    period: str = Query("monthly"),
):
    if period not in {"daily", "monthly", "yearly"}:
        return JSONResponse(status_code=400, content={"error": "Invalid period"})

    date_func = {
        "daily": func.date(models.Review.created_at),
        "monthly": func.date_trunc("month", models.Review.created_at),
        "yearly": func.date_trunc("year", models.Review.created_at),
    }[period]

    query = (
        select(date_func.label("period"), func.avg(models.Review.rating).label("avg_rating"))
        .group_by("period")
        .order_by("period")
    )
    result = await session.execute(query)
    trends = [{"period": str(r.period), "avg_rating": float(r.avg_rating)} for r in result.all()]
    return JSONResponse(content={"trends": trends})


# ---------------------------
# Reviewer Loyalty
# ---------------------------
@router.get("/reviewer-loyalty")
async def reviewer_loyalty(session: AsyncSession = Depends(get_session)):
    query = (
        select(models.Review.reviewer_id, func.count(models.Review.id).label("review_count"))
        .group_by(models.Review.reviewer_id)
        .order_by(func.count(models.Review.id).desc())
    )
    result = await session.execute(query)
    data = [{"reviewer_id": r.reviewer_id, "review_count": r.review_count} for r in result.all()]
    return JSONResponse(content={"reviewer_loyalty": data})


# ---------------------------
# Word Cloud
# ---------------------------
@router.get("/wordcloud")
async def wordcloud_data(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(models.Review.comment))
    comments = [r.comment for r in result.all() if r.comment]
    text = " ".join(comments)

    wc = WordCloud(width=800, height=400, background_color="white").generate(text)
    img_base64 = encode_image_to_base64(wc.to_image())
    return JSONResponse(content={"wordcloud": img_base64})


# ---------------------------
# Forecast Ratings (Linear Regression)
# ---------------------------
@router.get("/forecast")
async def ratings_forecast(
    session: AsyncSession = Depends(get_session),
    future_periods: int = Query(6),
):
    result = await session.execute(select(models.Review.created_at, models.Review.rating))
    data = result.all()
    if not data:
        return JSONResponse(content={"forecast": []})

    dates = np.array([r.created_at.timestamp() for r in data]).reshape(-1, 1)
    ratings = np.array([r.rating for r in data])
    model = LinearRegression()
    model.fit(dates, ratings)

    last_timestamp = max(dates)[0]
    step = (max(dates) - min(dates)) / len(dates)
    future_dates = np.array([last_timestamp + step * (i + 1) for i in range(future_periods)]).reshape(-1, 1)
    predicted = model.predict(future_dates)

    forecast = [
        {"date": datetime.fromtimestamp(f).strftime("%Y-%m-%d"), "predicted_rating": round(p, 2)}
        for f, p in zip(future_dates.flatten(), predicted)
    ]
    return JSONResponse(content={"forecast": forecast})
