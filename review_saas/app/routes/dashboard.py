# filename: app/routes/dashboard.py
# ==========================================================
# REVIEW INTELLIGENCE DASHBOARD - FULLY INTEGRATED
# ==========================================================

from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from datetime import datetime
from typing import List
import os
import io

from app.core.db import get_session
from app.models import Review, Company
from app.utils.sentiment import analyze_sentiment, extract_keywords
from app.utils.pdf_report import generate_pdf_report
from app.utils.ai_chat import get_ai_response  # New AI module for proper chatbot responses

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

# ----------------------------------------------------------
# Load all companies for dropdown
# ----------------------------------------------------------
@router.get("/companies")
async def list_companies(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Company))
    companies = result.scalars().all()
    return [{"id": c.id, "name": c.name} for c in companies]

# ----------------------------------------------------------
# Overview KPIs: Total Reviews & Average Rating
# ----------------------------------------------------------
@router.get("/overview/{company_id}")
async def overview_kpis(
    company_id: int,
    session: AsyncSession = Depends(get_session)
):
    result = await session.execute(
        select(
            func.count(Review.id),
            func.avg(Review.rating)
        ).where(Review.company_id == company_id)
    )
    total, avg_rating = result.one()
    return {
        "total_reviews": total or 0,
        "average_rating": round(avg_rating or 0, 2)
    }

# ----------------------------------------------------------
# Insights Endpoint: Sentiment counts & top keywords
# ----------------------------------------------------------
@router.get("/insights")
async def insights(
    company_id: int = Query(...),
    start: str = Query("2010-01-01"),
    end: str = Query(None),
    session: AsyncSession = Depends(get_session)
):
    end_date = end or datetime.utcnow().strftime("%Y-%m-%d")
    start_dt = datetime.fromisoformat(start)
    end_dt = datetime.fromisoformat(end_date)

    result = await session.execute(
        select(Review.text, Review.rating)
        .where(and_(Review.company_id == company_id,
                    Review.date >= start_dt,
                    Review.date <= end_dt))
    )
    reviews = result.all()
    review_texts = [r[0] for r in reviews]

    # Sentiment analysis
    sentiment_counts = analyze_sentiment(review_texts)
    # Keyword extraction
    top_keywords = extract_keywords(review_texts)

    return {
        "sentiment_counts": sentiment_counts,
        "top_keywords": top_keywords
    }

# ----------------------------------------------------------
# Revenue Risk Monitoring
# ----------------------------------------------------------
@router.get("/revenue")
async def revenue_risk(
    company_id: int = Query(...),
    session: AsyncSession = Depends(get_session)
):
    result = await session.execute(
        select(Review.rating).where(Review.company_id == company_id)
    )
    ratings = [r[0] for r in result.scalars().all()]
    total = len(ratings)
    if total == 0:
        return {"loss_probability": "—", "impact_level": "—", "reputation_score": "—"}

    negative_count = sum(1 for r in ratings if r < 3)
    loss_probability = round((negative_count / total) * 100, 2)
    impact_level = min(100, loss_probability * 1.2)
    reputation_score = round(5 - (negative_count / total * 2), 2)

    return {
        "loss_probability": f"{loss_probability}%",
        "impact_level": f"{impact_level}%",
        "reputation_score": reputation_score
    }

# ----------------------------------------------------------
# Chatbot Endpoint for AI questions
# ----------------------------------------------------------
@router.get("/chatbot/explain")
async def chatbot(
    question: str = Query(...),
    company_id: int = Query(...),
    session: AsyncSession = Depends(get_session)
):
    result = await session.execute(
        select(Review.text).where(Review.company_id == company_id)
    )
    reviews = [r[0] for r in result.all()]

    # Generate AI response using reviews as context
    answer = get_ai_response(question=question, review_texts=reviews)

    return {"answer": answer}

# ----------------------------------------------------------
# PDF Report Download
# ----------------------------------------------------------
@router.get("/executive-report/pdf/{company_id}")
async def download_report(company_id: int, session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Review).where(Review.company_id == company_id))
    reviews = result.scalars().all()
    pdf_bytes = generate_pdf_report(reviews)

    # Serve PDF as downloadable file
    return FileResponse(
        path_or_file=io.BytesIO(pdf_bytes),
        media_type='application/pdf',
        filename=f"company_{company_id}_report.pdf"
    )

# ----------------------------------------------------------
# Reviewer Loyalty & Frequency (Bonus)
# ----------------------------------------------------------
@router.get("/reviewer-frequency/{company_id}")
async def reviewer_frequency(
    company_id: int,
    session: AsyncSession = Depends(get_session)
):
    result = await session.execute(
        select(Review.user_email, func.count(Review.id))
        .where(Review.company_id == company_id)
        .group_by(Review.user_email)
        .order_by(func.count(Review.id).desc())
    )
    data = [{"user_email": r[0], "review_count": r[1]} for r in result.all()]
    return {"reviewer_frequency": data}

# ----------------------------------------------------------
# Forecast Ratings Trend (Linear Regression)
# ----------------------------------------------------------
@router.get("/forecast/{company_id}")
async def forecast_ratings(
    company_id: int,
    session: AsyncSession = Depends(get_session)
):
    import numpy as np
    from sklearn.linear_model import LinearRegression

    result = await session.execute(
        select(Review.date, Review.rating).where(Review.company_id == company_id)
    )
    data = result.all()
    if not data:
        return {"forecast": []}

    dates = np.array([(d[0] - datetime(1970, 1, 1)).days for d in data]).reshape(-1, 1)
    ratings = np.array([d[1] for d in data])

    model = LinearRegression()
    model.fit(dates, ratings)
    future_days = np.array([dates[-1, 0] + i for i in range(1, 8)]).reshape(-1, 1)
    forecasted_ratings = model.predict(future_days).tolist()

    return {"forecast": forecasted_ratings}
