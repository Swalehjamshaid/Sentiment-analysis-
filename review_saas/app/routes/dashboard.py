# filename: app/routes/dashboard.py
# ==========================================================
# REVIEW INTELLIGENCE DASHBOARD — ENTERPRISE 100/100 VERSION
# ==========================================================

from __future__ import annotations

import io
import os
import logging
import asyncio
from datetime import datetime
from collections import Counter, defaultdict
from typing import Dict, List, Any, Optional

from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from fpdf import FPDF
from openai import OpenAI

from app.core.db import get_db
from app.core.models import Company, Review

# ----------------------------------------------------------
# CONFIG
# ----------------------------------------------------------
router = APIRouter(prefix="", tags=["Dashboard"])
logger = logging.getLogger("dashboard")

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

MAX_REVIEWS_FETCH = 5000
CACHE_TTL = 300  # seconds

NEGATIVE_RATINGS = {1, 2}
NEG_SENTIMENT_LIMIT = -0.2

STOPWORDS = {
    "the", "and", "with", "this", "that", "for", "from",
    "was", "were", "have", "has", "had", "very", "just",
    "they", "them", "their", "there", "but", "not", "are",
    "you", "your", "will", "can", "our", "all", "any"
}

# Simple in-memory cache (replace with Redis in prod)
CACHE: Dict[str, Dict[str, Any]] = {}

# ----------------------------------------------------------
# HELPERS
# ----------------------------------------------------------
def safe_date(val: Optional[str]) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(val) if val else None
    except Exception:
        return None


def sanitize_pdf(text: str) -> str:
    replacements = {
        "—": "-", "–": "-", "’": "'", "“": '"', "”": '"',
        "•": "-", "…": "...", "©": "(C)", "®": "(R)"
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
    return text


def clean_keywords(text: str) -> List[str]:
    words = []
    for w in text.lower().split():
        w = w.strip(".,!?()\"';:[]{}")
        if len(w) >= 4 and w.isalpha() and w not in STOPWORDS:
            words.append(w)
    return words


async def get_company(session: AsyncSession, company_id: int) -> Company:
    res = await session.execute(select(Company).where(Company.id == company_id))
    company = res.scalars().first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return company


def cache_get(key: str):
    entry = CACHE.get(key)
    if entry and (datetime.utcnow().timestamp() - entry["time"] < CACHE_TTL):
        return entry["data"]
    return None


def cache_set(key: str, data: Any):
    CACHE[key] = {"data": data, "time": datetime.utcnow().timestamp()}


# ----------------------------------------------------------
# CORE ANALYTICS ENGINE
# ----------------------------------------------------------
def compute_analytics(reviews: List[Review]) -> Dict[str, Any]:

    if not reviews:
        return {
            "total_reviews": 0,
            "average_rating": 0.0,
            "kpis": {},
            "visualizations": {},
            "risk": {}
        }

    ratings = []
    monthly_map = defaultdict(list)
    sentiment_counts = {"Positive": 0, "Neutral": 0, "Negative": 0}
    rating_distribution = {i: 0 for i in range(1, 6)}

    negative_count = 0
    severe_count = 0

    for r in reviews:

        if r.rating:
            rating = int(r.rating)
            ratings.append(rating)
            rating_distribution[rating] += 1

            if rating in NEGATIVE_RATINGS:
                severe_count += 1

        if r.sentiment_score is not None:
            if r.sentiment_score <= NEG_SENTIMENT_LIMIT:
                sentiment_counts["Negative"] += 1
                negative_count += 1
            elif r.sentiment_score >= abs(NEG_SENTIMENT_LIMIT):
                sentiment_counts["Positive"] += 1
            else:
                sentiment_counts["Neutral"] += 1

        if r.google_review_time and r.rating:
            key = r.google_review_time.strftime("%Y-%m")
            monthly_map[key].append(r.rating)

    total = len(reviews)
    avg_rating = round(sum(ratings) / len(ratings), 2) if ratings else 0.0

    risk_pct = round(((negative_count * 0.6 + severe_count * 0.4) / total) * 100, 1)

    churn_prediction = round(min(95, (negative_count / total) * 100), 1)
    loyalty_score = round((sentiment_counts["Positive"] / total) * 100, 1)

    monthly_trend = [
        {"month": k, "avg": round(sum(v)/len(v), 2), "count": len(v)}
        for k, v in sorted(monthly_map.items())
    ]

    return {
        "total_reviews": total,
        "average_rating": avg_rating,
        "kpis": {
            "churn_prediction": churn_prediction,
            "loyalty_score": loyalty_score,
            "reputation_score": max(0, 100 - risk_pct)
        },
        "visualizations": {
            "ratings": rating_distribution,
            "sentiment": sentiment_counts,
            "trend": monthly_trend
        },
        "risk": {
            "loss_probability": f"{risk_pct}%",
            "impact": "High" if risk_pct > 25 else "Medium" if risk_pct > 10 else "Low"
        }
    }


# ----------------------------------------------------------
# ROUTES
# ----------------------------------------------------------
@router.get("/overview/{company_id}")
async def overview(company_id: int, session: AsyncSession = Depends(get_db)):

    cache_key = f"overview_{company_id}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    await get_company(session, company_id)

    res = await session.execute(
        select(Review)
        .where(Review.company_id == company_id)
        .limit(MAX_REVIEWS_FETCH)
    )

    analytics = compute_analytics(res.scalars().all())

    data = {
        "total_reviews": analytics["total_reviews"],
        "average_rating": analytics["average_rating"]
    }

    cache_set(cache_key, data)
    return data


@router.get("/insights")
async def insights(
    company_id: int,
    start: Optional[str] = None,
    end: Optional[str] = None,
    session: AsyncSession = Depends(get_db),
):

    await get_company(session, company_id)

    stmt = select(Review).where(Review.company_id == company_id)

    if start_dt := safe_date(start):
        stmt = stmt.where(Review.google_review_time >= start_dt)

    if end_dt := safe_date(end):
        stmt = stmt.where(Review.google_review_time <= end_dt)

    stmt = stmt.limit(MAX_REVIEWS_FETCH)

    res = await session.execute(stmt)
    reviews = res.scalars().all()

    analytics = compute_analytics(reviews)

    keywords = []
    for r in reviews:
        if r.text:
            keywords.extend(clean_keywords(r.text))

    analytics["top_keywords"] = [
        w for w, _ in Counter(keywords).most_common(20)
    ]

    return analytics


@router.post("/chatbot/explain")
async def chatbot(
    question: str,
    company_id: int,
    session: AsyncSession = Depends(get_db),
):

    if len(question) > 500:
        raise HTTPException(status_code=400, detail="Question too long")

    res = await session.execute(
        select(Review)
        .where(Review.company_id == company_id)
        .limit(500)
    )

    analytics = compute_analytics(res.scalars().all())

    prompt = f"""
You are a senior business consultant.

KPIs:
- Reviews: {analytics['total_reviews']}
- Rating: {analytics['average_rating']}
- Risk: {analytics['risk']['loss_probability']}

Question: {question}

Give concise business advice.
"""

    try:
        response = await asyncio.to_thread(
            lambda: client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
            )
        )

        return {"answer": response.choices[0].message.content}

    except Exception as e:
        logger.error(f"AI error: {e}")
        return {"answer": "AI unavailable"}


@router.get("/executive-report/pdf/{company_id}")
async def executive_report(company_id: int, session: AsyncSession = Depends(get_db)):

    company = await get_company(session, company_id)

    res = await session.execute(
        select(Review)
        .where(Review.company_id == company_id)
        .limit(MAX_REVIEWS_FETCH)
    )

    analytics = compute_analytics(res.scalars().all())

    def generate_pdf():

        pdf = FPDF()
        pdf.add_page()

        pdf.set_font("Arial", "B", 16)
        pdf.cell(0, 10, sanitize_pdf(company.name), ln=True)

        pdf.set_font("Arial", "", 12)
        pdf.ln(5)

        pdf.cell(0, 10, f"Total Reviews: {analytics['total_reviews']}", ln=True)
        pdf.cell(0, 10, f"Average Rating: {analytics['average_rating']}", ln=True)
        pdf.cell(0, 10, f"Risk: {analytics['risk']['loss_probability']}", ln=True)

        return pdf.output(dest="S").encode("latin-1")

    buffer = io.BytesIO(await asyncio.to_thread(generate_pdf))

    return StreamingResponse(buffer, media_type="application/pdf")


@router.get("/recent-reviews/{company_id}")
async def recent_reviews(company_id: int, session: AsyncSession = Depends(get_db)):

    await get_company(session, company_id)

    res = await session.execute(
        select(Review)
        .where(Review.company_id == company_id)
        .order_by(desc(Review.google_review_time))
        .limit(100)
    )

    return [
        {
            "author": r.author_name or "Anonymous",
            "rating": r.rating,
            "text": r.text,
            "date": r.google_review_time.strftime("%Y-%m-%d") if r.google_review_time else "N/A"
        }
        for r in res.scalars()
    ]
