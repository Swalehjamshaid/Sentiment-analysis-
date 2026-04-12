# filename: app/routes/dashboard.py
# ==========================================================
# REVIEW INTELLIGENCE DASHBOARD — 100% FRONTEND INTEGRATED
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
router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])
logger = logging.getLogger("dashboard")

# Ensure your Environment Variable is set
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
                "reputation_score": 100.0
            },
            "visualizations": {
                "emotions": {"Positive": 0, "Neutral": 0, "Negative": 0},
                "ratings": {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0},
                "sentiment_trend": []
            },
            "risk": {
                "loss_probability": "0%",
                "impact_level": "None",
                "reputation_score": 100.0
            }
        }

    ratings: List[int] = []
    monthly_map: Dict[str, List[int]] = defaultdict(list)
    sentiment_counts = {"Positive": 0, "Neutral": 0, "Negative": 0}
    rating_distribution = {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0}
    severe_count = 0
    negative_count = 0

    for r in reviews:
        if r.rating:
            rating_val = int(r.rating)
            rating_distribution[str(rating_val)] += 1
            ratings.append(rating_val)

            if r.google_review_time:
                key = r.google_review_time.strftime("%b %Y")
                monthly_map[key].append(rating_val)

            if rating_val in NEGATIVE_RATINGS:
                severe_count += 1

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

    monthly_trend = []
    for k, v in monthly_map.items():
        dt = datetime.strptime(k, "%b %Y")
        monthly_trend.append({
            "month": k,
            "avg": round(sum(v) / len(v), 2),
            "dt": dt
        })

    monthly_trend.sort(key=lambda x: x["dt"])
    for t in monthly_trend:
        t.pop("dt")

    return {
        "metadata": {
            "total_reviews": total
        },
        "kpis": {
            "average_rating": avg_rating,
            "reputation_score": max(0.0, round(100 - risk_pct, 1))
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
        }
    }

# ==========================================================
# ROUTES
# ==========================================================

@router.get("/ai/insights", response_class=JSONResponse)
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

    # Keywords logic for Frontend
    keywords: List[str] = []
    for r in reviews:
        if r.text: keywords.extend(clean_keywords(r.text))
    
    analytics["top_keywords"] = [w for w, _ in Counter(keywords).most_common(10)]
    return analytics

@router.get("/revenue", response_class=JSONResponse)
async def revenue(company_id: int, session: AsyncSession = Depends(get_db)):
    """Specifically used by the frontend to update the Risk Monitoring card"""
    await get_company(session, company_id)
    res = await session.execute(select(Review).where(Review.company_id == company_id))
    analytics = compute_analytics(res.scalars().all())
    
    return {
        "risk_percent": analytics["risk"]["loss_probability"].replace("%", ""),
        "impact": analytics["risk"]["impact_level"],
        "reputation_score": analytics["kpis"]["reputation_score"]
    }

@router.post("/chat", response_class=JSONResponse)
async def chatbot(
    request_data: dict, 
    company_id: int = Query(...), 
    session: AsyncSession = Depends(get_db)
):
    """Handles logic for the Strategy Consultant AI Chat window"""
    question = request_data.get("message", "")
    res = await session.execute(select(Review).where(Review.company_id == company_id).limit(100))
    reviews = res.scalars().all()
    analytics = compute_analytics(reviews)

    prompt = (f"You are a Business Strategy Consultant. Analyze this data for Company ID {company_id}: "
              f"Total Reviews: {analytics['metadata']['total_reviews']}, "
              f"Average Rating: {analytics['kpis']['average_rating']}. "
              f"User Question: {question}")

    try:
        response = await asyncio.to_thread(
            lambda: openai.ChatCompletion.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
            )
        )
        return {"answer": response.choices[0].message.content.strip()}
    except Exception as e:
        logger.error(f"AI Error: {e}")
        return {"answer": "AI Engine is currently optimizing. Please try again shortly."}

@router.get("/executive-report/pdf/{company_id}")
async def executive_report(company_id: int, session: AsyncSession = Depends(get_db)):
    company = await get_company(session, company_id)
    res = await session.execute(select(Review).where(Review.company_id == company_id))
    analytics = compute_analytics(res.scalars().all())

    def generate_pdf() -> bytes:
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", "B", 16)
        pdf.cell(0, 10, sanitize_pdf(f"Executive Analysis: {company.name}"), ln=True, align="C")
        pdf.ln(10)
        pdf.set_font("Arial", "", 12)
        pdf.cell(0, 10, f"Analysis Date: {datetime.now().strftime('%Y-%m-%d')}", ln=True)
        pdf.cell(0, 10, f"Total Customer Reviews: {analytics['metadata']['total_reviews']}", ln=True)
        pdf.cell(0, 10, f"Overall Rating: {analytics['kpis']['average_rating']} / 5.0", ln=True)
        pdf.cell(0, 10, f"Brand Reputation Score: {analytics['kpis']['reputation_score']}%", ln=True)
        return pdf.output(dest="S")

    pdf_content = await asyncio.to_thread(generate_pdf)
    return StreamingResponse(io.BytesIO(pdf_content), media_type="application/pdf", 
                             headers={"Content-Disposition": f"attachment; filename=Report_{company_id}.pdf"})
