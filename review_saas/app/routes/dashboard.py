# filename: app/routes/dashboard.py
# ==========================================================
# REVIEW INTELLIGENCE DASHBOARD — CORRECTED & WORLD‑CLASS
# ==========================================================

from __future__ import annotations

import io
import os
import logging
from datetime import datetime
from collections import Counter, defaultdict
from typing import List, Dict

from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

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

NEGATIVE_CUTOFF = -0.25
POSITIVE_CUTOFF = 0.25


# ----------------------------------------------------------
# Helpers
# ----------------------------------------------------------
def safe_date(val: str | None):
    try:
        return datetime.fromisoformat(val) if val else None
    except Exception:
        return None


async def get_company(session: AsyncSession, cid: int) -> Company:
    res = await session.execute(select(Company).where(Company.id == cid))
    company = res.scalars().first()
    if not company:
        raise HTTPException(404, "Company not found")
    return company


def sentiment_bucket(score: float) -> str:
    if score <= NEGATIVE_CUTOFF:
        return "Negative"
    if score >= POSITIVE_CUTOFF:
        return "Positive"
    return "Neutral"


# ==========================================================
# 1. OVERVIEW
# ==========================================================
@router.get("/overview/{company_id}")
async def overview(company_id: int, session: AsyncSession = Depends(get_session)):
    await get_company(session, company_id)

    res = await session.execute(
        select(Review.rating).where(Review.company_id == company_id)
    )
    ratings = [r[0] for r in res.fetchall() if r[0]]

    total = len(ratings)
    avg = sum(ratings) / total if total else 0

    return {
        "total_reviews": total,
        "average_rating": round(avg, 2)
    }


# ==========================================================
# 2. INSIGHTS (ALL GRAPHS)
# ==========================================================
@router.get("/insights")
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

    # ---------- Sentiment Distribution ----------
    sentiment_counts = {"Positive": 0, "Neutral": 0, "Negative": 0}

    # ---------- Rating Distribution ----------
    rating_dist = {i: 0 for i in range(1, 6)}

    # ---------- Monthly Trend ----------
    month_map: Dict[str, List[int]] = defaultdict(list)

    # ---------- Keywords ----------
    words: List[str] = []

    for r in reviews:
        score = r.sentiment_score or 0
        bucket = sentiment_bucket(score)
        sentiment_counts[bucket] += 1

        if r.rating:
            rating_dist[int(r.rating)] += 1

        if r.google_review_time and r.rating:
            key = r.google_review_time.strftime("%b %Y")
            month_map[key].append(r.rating)

        if r.text:
            words.extend(
                w for w in r.text.lower().split()
                if len(w) > 4
            )

    monthly_trend = [
        {
            "month": k,
            "avg": round(sum(v) / len(v), 2),
            "count": len(v)
        }
        for k, v in sorted(month_map.items())
    ]

    top_keywords = [
        w for w, _ in Counter(words).most_common(12)
    ]

    return {
        "sentiment_counts": sentiment_counts,
        "rating_distribution": rating_dist,
        "monthly_trend": monthly_trend,
        "top_keywords": top_keywords
    }


# ==========================================================
# 3. REVENUE RISK (CORRECTED)
# ==========================================================
@router.get("/revenue")
async def revenue(company_id: int, session: AsyncSession = Depends(get_session)):
    await get_company(session, company_id)

    res = await session.execute(
        select(Review.sentiment_score).where(Review.company_id == company_id)
    )
    scores = [s[0] for s in res.fetchall() if s[0] is not None]

    if not scores:
        return {
            "loss_probability": "0%",
            "impact_level": "None",
            "reputation_score": 100
        }

    weighted_neg = sum(abs(s) for s in scores if s <= NEGATIVE_CUTOFF)
    total_weight = sum(abs(s) for s in scores)

    risk = (weighted_neg / total_weight) * 100 if total_weight else 0

    reputation = max(0, round(100 - risk, 1))

    return {
        "loss_probability": f"{round(risk, 1)}%",
        "impact_level": "High" if risk > 25 else "Medium" if risk > 12 else "Low",
        "reputation_score": reputation
    }


# ==========================================================
# 4. CHATBOT (FULLY WORKING)
# ==========================================================
@router.post("/chatbot/explain")
async def chatbot(question: str = Query(...)):
    try:
        res = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are an expert business analyst."},
                {"role": "user", "content": question}
            ],
            temperature=0.3,
            timeout=10
        )
        return {"answer": res.choices[0].message.content.strip()}
    except Exception as e:
        logger.error(e)
        return {"answer": "AI service temporarily unavailable."}


# ==========================================================
# 5. EXECUTIVE PDF
# ==========================================================
@router.get("/executive-report/pdf/{company_id}")
async def pdf(company_id: int, session: AsyncSession = Depends(get_session)):
    company = await get_company(session, company_id)

    res = await session.execute(
        select(Review.rating).where(Review.company_id == company_id)
    )
    ratings = [r[0] for r in res.fetchall() if r[0]]

    avg = sum(ratings) / len(ratings) if ratings else 0

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, f"Executive Report — {company.name}", ln=True, align="C")
    pdf.ln(10)
    pdf.set_font("Arial", size=12)
    pdf.cell(0, 8, f"Total Reviews: {len(ratings)}", ln=True)
    pdf.cell(0, 8, f"Average Rating: {round(avg,2)}", ln=True)

    buffer = io.BytesIO(pdf.output(dest="S").encode("latin-1"))

    return FileResponse(
        buffer,
        media_type="application/pdf",
        filename=f"Executive_Report_{company_id}.pdf"
    )
