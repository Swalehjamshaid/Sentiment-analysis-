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
import io
import os

# ------------------- Core Imports -------------------
from app.core.db import get_session
from app.core.models import Review, Company  # ✅ Fixed import path
from app.utils.sentiment import analyze_sentiment, extract_keywords
from app.utils.pdf_report import generate_pdf_report

# ------------------- Router -------------------
router = APIRouter(prefix="/api")

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
        select(func.count(Review.id), func.avg(Review.rating))
        .where(Review.company_id == company_id)
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
# Revenue Risk Monitoring (Dummy Computation Example)
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

    # Placeholder AI response logic
    if not reviews:
        response = "No reviews available for this company."
    elif "rating" in question.lower():
        avg_rating = round(sum([len(r) for r in reviews])/len(reviews), 2) if reviews else 0
        response = f"The average rating is {avg_rating}."
    elif "sentiment" in question.lower():
        response = "Most reviews are positive based on AI sentiment analysis."
    else:
        response = "I recommend focusing on reviews with low ratings for improvement."

    return {"answer": response}

# ----------------------------------------------------------
# PDF Report Download
# ----------------------------------------------------------
@router.get("/executive-report/pdf/{company_id}")
async def download_report(company_id: int, session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Review).where(Review.company_id == company_id))
    reviews = result.scalars().all()
    pdf_bytes = generate_pdf_report(reviews)

    return FileResponse(
        path_or_file=io.BytesIO(pdf_bytes),
        media_type='application/pdf',
        filename=f"company_{company_id}_report.pdf"
    )
