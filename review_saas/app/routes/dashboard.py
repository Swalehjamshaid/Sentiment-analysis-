# filename: app/routes/dashboard.py
# ==========================================================
# REVIEW INTELLIGENCE – WORLD CLASS DASHBOARD BACKEND
# ==========================================================

from __future__ import annotations

import io
import os
import logging
from datetime import datetime
from collections import Counter, defaultdict
from typing import Dict, List

from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from fpdf import FPDF
import openai

from app.core.db import get_session
from app.core.models import Company, Review

# ----------------------------------------------------------
# Setup
# ----------------------------------------------------------
router = APIRouter(prefix="", tags=["Dashboard"])
logger = logging.getLogger("app.dashboard")

openai.api_key = os.getenv("OPENAI_API_KEY")

# ----------------------------------------------------------
# Helpers
# ----------------------------------------------------------

def safe_date(value: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(value) if value else None
    except Exception:
        return None


async def load_company(session: AsyncSession, company_id: int) -> Company:
    res = await session.execute(select(Company).where(Company.id == company_id))
    company = res.scalars().first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return company


async def fetch_reviews(
    session: AsyncSession, company_id: int, start_dt=None, end_dt=None
) -> List[Review]:
    stmt = select(Review).where(Review.company_id == company_id)
    if start_dt:
        stmt = stmt.where(Review.google_review_time >= start_dt)
    if end_dt:
        stmt = stmt.where(Review.google_review_time <= end_dt)
    res = await session.execute(stmt)
    return res.scalars().all()


def sentiment_bucket(score: float) -> str:
    if score >= 0.25:
        return "Positive"
    if score <= -0.25:
        return "Negative"
    return "Neutral"


# ==========================================================
# 1. /api/overview/{company_id}
# ==========================================================
@router.get("/overview/{company_id}", response_class=JSONResponse)
async def overview(company_id: int, session: AsyncSession = Depends(get_session)):
    await load_company(session, company_id)

    res = await session.execute(
        select(func.count(Review.id), func.avg(Review.rating))
        .where(Review.company_id == company_id)
    )
    total, avg = res.first()

    return {
        "total_reviews": int(total or 0),
        "average_rating": round(float(avg or 0), 2),
    }


# ==========================================================
# 2. /api/insights
# ==========================================================
@router.get("/insights", response_class=JSONResponse)
async def insights(
    company_id: int = Query(...),
    start: str | None = Query(None),
    end: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
):
    await load_company(session, company_id)

    start_dt = safe_date(start)
    end_dt = safe_date(end)

    reviews = await fetch_reviews(session, company_id, start_dt, end_dt)

    # ---------------- Sentiment Count
    sentiment_counts: Dict[str, int] = {"Positive": 0, "Neutral": 0, "Negative": 0}

    # ---------------- Rating Distribution
    rating_distribution = {i: 0 for i in range(1, 6)}

    # ---------------- Monthly Trend
    monthly_map: Dict[str, List[int]] = defaultdict(list)

    # ---------------- Keywords
    words: List[str] = []

    for r in reviews:
        score = r.sentiment_score or 0.0
        bucket = sentiment_bucket(score)
        sentiment_counts[bucket] += 1

        if r.rating:
            rating_distribution[int(r.rating)] += 1

        if r.text:
            words.extend(r.text.lower().split())

        if r.google_review_time:
            key = r.google_review_time.strftime("%b %Y")
            monthly_map[key].append(r.rating or 0)

    monthly_trend = [
        {"month": k, "avg": round(sum(v) / len(v), 2)}
        for k, v in sorted(monthly_map.items())
        if v
    ]

    top_keywords = [
        w for w, _ in Counter(words).most_common(12)
    ]

    return {
        "sentiment_counts": sentiment_counts,
        "rating_distribution": rating_distribution,
        "monthly_trend": monthly_trend,
        "top_keywords": top_keywords,
    }


# ==========================================================
# 3. /api/revenue
# ==========================================================
@router.get("/revenue", response_class=JSONResponse)
async def revenue(
    company_id: int = Query(...), session: AsyncSession = Depends(get_session)
):
    await load_company(session, company_id)

    reviews = await session.execute(
        select(Review.sentiment_score).where(Review.company_id == company_id)
    )
    scores = [r[0] for r in reviews.fetchall() if r[0] is not None]

    if not scores:
        return {
            "loss_probability": "0%",
            "impact_level": "None",
            "reputation_score": 100,
        }

    negative = len([s for s in scores if s <= -0.25])
    risk = (negative / len(scores)) * 100

    return {
        "loss_probability": f"{round(risk, 1)}%",
        "impact_level": "High" if risk > 20 else "Medium" if risk > 10 else "Low",
        "reputation_score": round(100 - risk, 1),
    }


# ==========================================================
# 4. /api/chatbot/explain  ✅ WORKING
# ==========================================================
@router.post("/chatbot/explain", response_class=JSONResponse)
async def chatbot_explain(
    question: str = Query(...),
    company_id: int | None = Query(None),
):
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You are a senior business consultant. "
                               "Give actionable advice based on customer reviews."
                },
                {"role": "user", "content": question},
            ],
            temperature=0.2,
            timeout=10
        )
        return {"answer": response.choices[0].message.content.strip()}
    except Exception as exc:
        logger.error(f"Chatbot failure: {exc}")
        return {"answer": "AI service is temporarily unavailable."}


# ==========================================================
# 5. /api/executive-report/pdf/{company_id}
# ==========================================================
@router.get("/executive-report/pdf/{company_id}")
async def executive_report(
    company_id: int, session: AsyncSession = Depends(get_session)
):
    company = await load_company(session, company_id)
    reviews = await fetch_reviews(session, company_id)

    avg_rating = (
        sum(r.rating or 0 for r in reviews) / len(reviews) if reviews else 0
    )

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, f"Executive Review Report — {company.name}", ln=True, align="C")
    pdf.ln(10)

    pdf.set_font("Arial", size=12)
    pdf.cell(0, 8, f"Total Reviews: {len(reviews)}", ln=True)
    pdf.cell(0, 8, f"Average Rating: {round(avg_rating, 2)}", ln=True)

    buffer = io.BytesIO(pdf.output(dest="S").encode("latin-1"))

    return FileResponse(
        buffer,
        media_type="application/pdf",
        filename=f"Executive_Report_{company_id}.pdf"
    )
