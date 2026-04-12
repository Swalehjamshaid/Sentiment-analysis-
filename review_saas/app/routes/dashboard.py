# filename: app/routes/dashboard.py
# ==========================================================
# REVIEW INTELLIGENCE DASHBOARD — WORLD CLASS ENTERPRISE UPDATED (ASYNC SAFE)
# ==========================================================

from __future__ import annotations

import io
import os
import logging
import asyncio
from datetime import datetime
from collections import Counter, defaultdict
from typing import Dict, List, Any

from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from fpdf import FPDF
import openai

from app.core.db import get_db
from app.core.models import Company, Review

# ----------------------------------------------------------
# Configuration
# ----------------------------------------------------------
router = APIRouter(prefix="", tags=["Dashboard"])
logger = logging.getLogger("dashboard")

# Ensure your Environment Variable is set in Railway
openai.api_key = os.getenv("OPENAI_API_KEY")

NEGATIVE_RATINGS = {1, 2}
NEG_SENTIMENT_LIMIT = -0.2

STOPWORDS = {
    "the", "and", "with", "this", "that", "for", "from",
    "was", "were", "have", "has", "had", "very", "just",
    "they", "them", "their", "there", "but", "not", "are",
    "you", "your", "will", "can", "our", "all", "any"
}

# ----------------------------------------------------------
# Helpers
# ----------------------------------------------------------
def safe_date(val: str | None) -> datetime | None:
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
    words: List[str] = []
    if not text:
        return words
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

# ----------------------------------------------------------
# CORE ANALYTICS ENGINE — 100% ALIGNED WITH FRONTEND KEYS
# ----------------------------------------------------------
def compute_analytics(reviews: List[Review]) -> Dict[str, Any]:
    # Default structure for empty states
    if not reviews:
        return {
            "metadata": {"total_reviews": 0},
            "kpis": {
                "average_rating": 0.0,
                "churn_prediction": 0.0,
                "loyalty_score": 0.0,
                "reputation_score": 100.0
            },
            "visualizations": {
                "emotions": {"Positive": 0, "Neutral": 0, "Negative": 0},
                "ratings": {1: 0, 2: 0, 3: 0, 4: 0, 5: 0},
                "sentiment_trend": []
            },
            "risk": {
                "loss_probability": "0%",
                "impact_level": "None",
                "reputation_score": 100.0
            },
            "negative_reviews": [],
            "total_reviews": 0,
            "average_rating": 0.0
        }

    ratings: List[int] = []
    monthly_map: Dict[str, List[int]] = defaultdict(list)
    sentiment_counts = {"Positive": 0, "Neutral": 0, "Negative": 0}
    rating_distribution = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    severe_count = 0
    negative_count = 0
    negative_reviews: List[Dict[str, Any]] = []

    for r in reviews:
        if r.rating:
            rating_val = int(r.rating)
            rating_distribution[rating_val] += 1
            ratings.append(rating_val)

            if r.google_review_time:
                key = r.google_review_time.strftime("%b %Y")
                monthly_map[key].append(rating_val)

            if rating_val in NEGATIVE_RATINGS:
                severe_count += 1
                if r.text and len(negative_reviews) < 10:
                    negative_reviews.append({
                        "author": r.author_name or "Anonymous",
                        "rating": r.rating,
                        "text": r.text[:180] + ("..." if len(r.text) > 180 else ""),
                        "date": r.google_review_time.strftime("%Y-%m-%d") if r.google_review_time else "N/A"
                    })

        if r.sentiment_score is not None:
            if r.sentiment_score <= NEG_SENTIMENT_LIMIT:
                sentiment_counts["Negative"] += 1
                negative_count += 1
            elif r.sentiment_score >= abs(NEG_SENTIMENT_LIMIT):
                sentiment_counts["Positive"] += 1
            else:
                sentiment_counts["Neutral"] += 1

    total = len(reviews)
    avg_rating = round(sum(ratings) / len(ratings), 2) if ratings else 0.0

    raw_risk = (negative_count * 0.6 + severe_count * 0.4) / total if total else 0
    risk_pct = round(raw_risk * 100, 1)

    churn_prediction = (
        round(min(95.0, (negative_count / total * 65) + (severe_count / total * 35)), 1)
        if total else 0.0
    )

    loyalty_score = (
        round((sentiment_counts["Positive"] / total) * 100, 1)
        if total else 0.0
    )

    monthly_trend = []
    for k, v in monthly_map.items():
        dt = datetime.strptime(k, "%b %Y")
        monthly_trend.append({
            "month": k,
            "avg": round(sum(v) / len(v), 2),
            "count": len(v),
            "dt": dt
        })

    monthly_trend.sort(key=lambda x: x["dt"])
    for t in monthly_trend:
        t.pop("dt")

    # This dictionary structure is specifically built to feed Dashboard.html
    return {
        "metadata": {
            "total_reviews": total
        },
        "kpis": {
            "average_rating": avg_rating,
            "reputation_score": max(0.0, round(100 - risk_pct, 1)),
            "churn_prediction": churn_prediction,
            "loyalty_score": loyalty_score
        },
        "visualizations": {
            "emotions": sentiment_counts,
            "ratings": rating_distribution,
            "sentiment_trend": monthly_trend
        },
        "risk": {
            "loss_probability": f"{risk_pct}%",
            "impact_level": "High" if risk_pct > 25 else "Medium" if risk_pct > 12 else "Low",
            "reputation_score": max(0.0, round(100 - risk_pct, 1))
        },
        "negative_reviews": negative_reviews,
        "total_reviews": total,
        "average_rating": avg_rating,
        "churn_prediction": churn_prediction,
        "loyalty_score": loyalty_score
    }

# ==========================================================
# ROUTES
# ==========================================================

@router.get("/insights", response_class=JSONResponse)
async def insights(
    company_id: int = Query(...),
    start: str | None = Query(None),
    end: str | None = Query(None),
    session: AsyncSession = Depends(get_db)
):
    await get_company(session, company_id)

    stmt = select(Review).where(Review.company_id == company_id)
    start_dt, end_dt = safe_date(start), safe_date(end)

    if start_dt: stmt = stmt.where(Review.google_review_time >= start_dt)
    if end_dt: stmt = stmt.where(Review.google_review_time <= end_dt)

    res = await session.execute(stmt)
    reviews = res.scalars().all()
    analytics = compute_analytics(reviews)

    # Keywords logic
    keywords: List[str] = []
    for r in reviews:
        if r.text: keywords.extend(clean_keywords(r.text))
    
    analytics["top_keywords"] = [w for w, _ in Counter(keywords).most_common(30)]
    return analytics


@router.get("/revenue", response_class=JSONResponse)
async def revenue(company_id: int, session: AsyncSession = Depends(get_db)):
    await get_company(session, company_id)
    res = await session.execute(select(Review).where(Review.company_id == company_id))
    analytics = compute_analytics(res.scalars().all())
    
    # Matching the specific keys used in Dashboard.html: uiSet("riskPct", ...)
    return {
        "risk_percent": analytics["risk"]["loss_probability"].replace("%", ""),
        "impact": analytics["risk"]["impact_level"],
        "reputation_score": analytics["kpis"]["reputation_score"]
    }


@router.post("/chatbot/explain", response_class=JSONResponse)
async def chatbot(
    request_data: dict, 
    company_id: int = Query(...), 
    session: AsyncSession = Depends(get_db)
):
    question = request_data.get("message", "")
    res = await session.execute(select(Review).where(Review.company_id == company_id).limit(250))
    reviews = res.scalars().all()
    analytics = compute_analytics(reviews)

    prompt = f"Strategy Consultant mode. Data: {analytics['total_reviews']} reviews, {analytics['average_rating']} rating. Question: {question}"

    try:
        response = await asyncio.to_thread(
            lambda: openai.ChatCompletion.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.25,
            )
        )
        return {"answer": response.choices[0].message.content.strip()}
    except Exception as e:
        logger.error(f"AI Error: {e}")
        return {"answer": "Strategic analysis engine is calibrating. Please retry in a moment."}


@router.get("/recent-reviews/{company_id}", response_class=JSONResponse)
async def get_recent_reviews(company_id: int, session: AsyncSession = Depends(get_db)):
    await get_company(session, company_id)
    stmt = select(Review).where(Review.company_id == company_id).order_by(desc(Review.google_review_time)).limit(100)
    res = await session.execute(stmt)
    
    return [
        {
            "author": r.author_name or "Anonymous",
            "rating": r.rating,
            "text": r.text,
            "date": r.google_review_time.strftime("%Y-%m-%d") if r.google_review_time else "N/A",
        }
        for r in res.scalars().all()
    ]


@router.get("/executive-report/pdf/{company_id}")
async def executive_report(company_id: int, session: AsyncSession = Depends(get_db)):
    company = await get_company(session, company_id)
    res = await session.execute(select(Review).where(Review.company_id == company_id))
    analytics = compute_analytics(res.scalars().all())

    def generate_pdf() -> bytes:
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", "B", 16)
        pdf.cell(0, 10, sanitize_pdf(f"Executive Report: {company.name}"), ln=True, align="C")
        pdf.set_font("Arial", "", 12)
        pdf.cell(0, 10, f"Total Reviews: {analytics['total_reviews']}", ln=True)
        return pdf.output(dest="S")

    pdf_content = await asyncio.to_thread(generate_pdf)
    return StreamingResponse(io.BytesIO(pdf_content), media_type="application/pdf")
