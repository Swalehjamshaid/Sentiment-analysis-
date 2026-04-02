# filename: app/routes/dashboard.py
# ==========================================================
# REVIEW INTELLIGENCE DASHBOARD — FINAL REFINED (NO LOSS)
# ==========================================================

from __future__ import annotations

import io
import os
import logging
from datetime import datetime
from collections import Counter, defaultdict
from typing import Dict, List

from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc # Added desc for sorting

from fpdf import FPDF
import openai

from app.core.db import get_session
from app.core.models import Company, Review

# ----------------------------------------------------------
# Setup
# ----------------------------------------------------------
router = APIRouter(prefix="", tags=["Dashboard"])
logger = logging.getLogger("dashboard")
openai.api_key = os.getenv("OPENAI_API_KEY")

NEGATIVE_RATINGS = {1, 2}
NEG_SENTIMENT_LIMIT = -0.2

STOPWORDS = {
    "the", "and", "with", "this", "that", "for", "from",
    "was", "were", "have", "has", "had", "very", "just",
    "they", "them", "their", "there"
}

# ----------------------------------------------------------
# Helpers
# ----------------------------------------------------------
def safe_date(val: str | None):
    try:
        return datetime.fromisoformat(val) if val else None
    except Exception:
        return None


def clean_keywords(text: str) -> List[str]:
    words = []
    for w in text.lower().split():
        w = w.strip(".,!?()")
        if len(w) >= 4 and w not in STOPWORDS and w.isalpha():
            words.append(w)
    return words


async def get_company(session: AsyncSession, company_id: int) -> Company:
    res = await session.execute(select(Company).where(Company.id == company_id))
    company = res.scalars().first()
    if not company:
        raise HTTPException(404, "Company not found")
    return company


# ==========================================================
# 1. OVERVIEW
# ==========================================================
@router.get("/overview/{company_id}", response_class=JSONResponse)
async def overview(company_id: int, session: AsyncSession = Depends(get_session)):
    await get_company(session, company_id)

    res = await session.execute(
        select(Review.rating).where(Review.company_id == company_id)
    )
    ratings = [r[0] for r in res.fetchall() if r[0] is not None]

    total = len(ratings)
    avg_rating = round(sum(ratings) / total, 2) if total else 0

    return {
        "total_reviews": total,
        "average_rating": avg_rating
    }


# ==========================================================
# 2. INSIGHTS (ENHANCED)
# ==========================================================
@router.get("/insights", response_class=JSONResponse)
async def insights(
    company_id: int = Query(...),
    start: str | None = Query(None),
    end: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
):
    await get_company(session, company_id)

    start_dt = safe_date(start)
    end_dt = safe_date(end)

    stmt = select(Review).where(Review.company_id == company_id)
    if start_dt:
        stmt = stmt.where(Review.google_review_time >= start_dt)
    if end_dt:
        stmt = stmt.where(Review.google_review_time <= end_dt)

    res = await session.execute(stmt)
    reviews = res.scalars().all()

    sentiment_counts = {"Positive": 0, "Neutral": 0, "Negative": 0}
    rating_distribution = {i: 0 for i in range(1, 6)}
    monthly_map: Dict[str, List[int]] = defaultdict(list)
    keywords: List[str] = []

    for r in reviews:
        score = r.sentiment_score or 0

        if score <= NEG_SENTIMENT_LIMIT:
            sentiment_counts["Negative"] += 1
        elif score >= abs(NEG_SENTIMENT_LIMIT):
            sentiment_counts["Positive"] += 1
        else:
            sentiment_counts["Neutral"] += 1

        if r.rating:
            rating_distribution[int(r.rating)] += 1

        if r.rating and r.google_review_time:
            k = r.google_review_time.strftime("%b %Y")
            monthly_map[k].append(r.rating)

        if r.text:
            keywords.extend(clean_keywords(r.text))

    monthly_trend = [
        {
            "month": k,
            "avg": round(sum(v) / len(v), 2),
            "count": len(v)
        }
        for k, v in sorted(monthly_map.items())
    ]

    top_keywords = [word for word, _ in Counter(keywords).most_common(20)]

    return {
        "sentiment_counts": sentiment_counts,
        "rating_distribution": rating_distribution,
        "monthly_trend": monthly_trend,
        "top_keywords": top_keywords
    }


# ==========================================================
# 3. REVENUE RISK (SMART)
# ==========================================================
@router.get("/revenue", response_class=JSONResponse)
async def revenue(company_id: int, session: AsyncSession = Depends(get_session)):
    await get_company(session, company_id)

    res = await session.execute(
        select(Review.rating, Review.sentiment_score)
        .where(Review.company_id == company_id)
    )
    rows = res.fetchall()

    if not rows:
        return {
            "loss_probability": "0%",
            "impact_level": "None",
            "reputation_score": 100
        }

    negative_reviews = 0
    severe_reviews = 0

    for rating, sentiment in rows:
        if sentiment is not None and sentiment <= NEG_SENTIMENT_LIMIT:
            negative_reviews += 1
        if rating in NEGATIVE_RATINGS:
            severe_reviews += 1

    total = len(rows)
    raw_risk = (negative_reviews * 0.6 + severe_reviews * 0.4) / total

    risk_pct = round(raw_risk * 100, 1)
    reputation = max(0, round(100 - risk_pct, 1))

    return {
        "loss_probability": f"{risk_pct}%",
        "impact_level": "High" if risk_pct > 25 else "Medium" if risk_pct > 12 else "Low",
        "reputation_score": reputation
    }


# ==========================================================
# 4. 🤖 CHATBOT (NOW DATA-AWARE 🔥)
# ==========================================================
@router.post("/chatbot/explain", response_class=JSONResponse)
async def chatbot(
    question: str = Query(...),
    company_id: int = Query(...),
    session: AsyncSession = Depends(get_session)
):
    try:
        # Fetch company data
        res = await session.execute(
            select(Review.text, Review.rating)
            .where(Review.company_id == company_id)
            .limit(100)
        )
        reviews = res.fetchall()

        context = "\n".join([f"Rating:{r[1]} | {r[0]}" for r in reviews if r[0]])

        prompt = f"""
        You are a business consultant AI.

        Analyze this review data:
        {context}

        Question:
        {question}

        Give clear, actionable insights.
        """

        response = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3
        )

        return {"answer": response.choices[0].message.content.strip()}

    except Exception as e:
        logger.error(e)
        return {"answer": "AI service temporarily unavailable."}


# ==========================================================
# 5. 📊 AI EXECUTIVE SUMMARY (NEW 🔥🔥🔥)
# ==========================================================
@router.get("/ai-summary/{company_id}")
async def ai_summary(company_id: int, session: AsyncSession = Depends(get_session)):
    await get_company(session, company_id)

    res = await session.execute(
        select(Review.rating, Review.sentiment_score)
        .where(Review.company_id == company_id)
    )
    rows = res.fetchall()

    if not rows:
        return {"summary": "No sufficient data available."}

    ratings = [r[0] for r in rows if r[0] is not None]
    sentiments = [r[1] for r in rows if r[1] is not None]

    avg_rating = round(sum(ratings) / len(ratings), 2) if ratings else 0
    avg_sentiment = round(sum(sentiments) / len(sentiments), 2) if sentiments else 0

    summary = f"""
    Business Performance Summary:

    • Average Rating: {avg_rating}
    • Sentiment Score: {avg_sentiment}

    Insights:
    - Customer satisfaction is {"strong" if avg_rating > 4 else "moderate" if avg_rating > 3 else "weak"}
    - Sentiment indicates {"positive growth" if avg_sentiment > 0 else "potential issues"}

    Recommendation:
    - Focus on improving low-rating reviews
    - Strengthen positive feedback areas
    """

    return {"summary": summary.strip()}


# ==========================================================
# 6. PDF REPORT (UNCHANGED BUT CLEAN)
# ==========================================================
@router.get("/executive-report/pdf/{company_id}")
async def executive_report(company_id: int, session: AsyncSession = Depends(get_session)):
    company = await get_company(session, company_id)

    res = await session.execute(
        select(Review.rating).where(Review.company_id == company_id)
    )
    ratings = [r[0] for r in res.fetchall() if r[0] is not None]

    avg = round(sum(ratings) / len(ratings), 2) if ratings else 0

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, f"Executive Report — {company.name}", ln=True, align="C")
    pdf.ln(10)

    pdf.set_font("Arial", size=12)
    pdf.cell(0, 8, f"Total Reviews: {len(ratings)}", ln=True)
    pdf.cell(0, 8, f"Average Rating: {avg}", ln=True)
    pdf.cell(0, 8, f"Generated On: {datetime.utcnow().strftime('%Y-%m-%d')}", ln=True)

    buffer = io.BytesIO(pdf.output(dest="S").encode("latin-1"))

    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=Executive_Report_{company_id}.pdf"
        }
    )

# ==========================================================
# 7. RECENT REVIEWS (FOR DASHBOARD LISTING)
# ==========================================================
@router.get("/recent-reviews/{company_id}", response_class=JSONResponse)
async def get_recent_reviews(company_id: int, session: AsyncSession = Depends(get_session)):
    """ Returns the 100 most recent reviews for the dashboard display. """
    await get_company(session, company_id)

    # Query for the latest 100 reviews sorted by time descending
    stmt = (
        select(
            Review.author_name, 
            Review.rating, 
            Review.text, 
            Review.google_review_time
        )
        .where(Review.company_id == company_id)
        .order_by(desc(Review.google_review_time))
        .limit(100)
    )
    
    res = await session.execute(stmt)
    reviews = res.fetchall()

    return [
        {
            "author": r.author_name,
            "rating": r.rating,
            "text": r.text,
            "date": r.google_review_time.strftime("%Y-%m-%d") if r.google_review_time else "N/A"
        }
        for r in reviews
    ]
