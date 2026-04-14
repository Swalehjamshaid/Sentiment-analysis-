# ==========================================================
# filename: app/routes/dashboard.py
# ==========================================================
# REVIEW INTELLIGENCE AI – DASHBOARD BACKEND (100% MATCH)
# Fully aligned with provided frontend
# ==========================================================

from __future__ import annotations

import os
import re
import io
import asyncio
import logging
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Optional, Dict, List, Any

from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
import httpx
from fpdf import FPDF

from app.core.db import get_db
from app.core.models import Company, Review

# ----------------------------------------------------------
# Router
# ----------------------------------------------------------
router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])
logger = logging.getLogger("dashboard")

# ----------------------------------------------------------
# AI (DeepSeek)
# ----------------------------------------------------------
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"

# ----------------------------------------------------------
# Constants
# ----------------------------------------------------------
NEGATIVE_RATINGS = {1, 2}

EMOTION_KEYWORDS = {
    "Joy": ["happy", "great", "amazing", "excellent", "love", "awesome"],
    "Anger": ["angry", "worst", "terrible", "awful", "hate", "poor"],
    "Sadness": ["sad", "disappointed", "unhappy", "regret"],
    "Surprise": ["surprised", "wow", "unexpected"],
    "Fear": ["scared", "afraid", "unsafe", "risky"],
    "Love": ["love", "adore", "grateful", "thankful"]
}

# ----------------------------------------------------------
# Helpers
# ----------------------------------------------------------
def safe_date(val: Optional[str]) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(val) if val else None
    except Exception:
        return None

def sentiment_label(rating: Optional[int]) -> str:
    if rating is None:
        return "neutral"
    if rating <= 2:
        return "negative"
    if rating >= 4:
        return "positive"
    return "neutral"

def emotion_scores(text: str) -> Dict[str, int]:
    text = (text or "").lower()
    scores = {}
    for emotion, kws in EMOTION_KEYWORDS.items():
        scores[emotion] = min(sum(text.count(k) for k in kws) * 5, 100)
    return scores

async def get_company(session: AsyncSession, company_id: int) -> Company:
    c = (await session.execute(
        select(Company).where(Company.id == company_id)
    )).scalars().first()
    if not c:
        raise HTTPException(404, "Company not found")
    return c

# ----------------------------------------------------------
# Core Analytics
# ----------------------------------------------------------
def compute_analytics(reviews: List[Review]) -> Dict[str, Any]:
    total = len(reviews)
    ratings_dist = {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0}
    ratings = []
    negative = 0

    emotions_bucket = defaultdict(list)
    weekly = defaultdict(list)

    for r in reviews:
        if r.rating:
            ratings_dist[str(r.rating)] += 1
            ratings.append(r.rating)
            if r.rating in NEGATIVE_RATINGS:
                negative += 1

        if r.text:
            for e, v in emotion_scores(r.text).items():
                emotions_bucket[e].append(v)

        if r.google_review_time:
            week = (r.google_review_time - timedelta(days=r.google_review_time.weekday()))
            weekly[week.strftime("%Y-%m-%d")].append(r.rating or 3)

    avg_rating = round(sum(ratings) / len(ratings), 2) if ratings else 0.0
    risk_pct = round((negative / total) * 100, 1) if total else 0

    sentiment_trend = [
        {"week": k, "avg": round(sum(v) / len(v), 2)}
        for k, v in sorted(weekly.items())[-12:]
    ]

    return {
        "metadata": {
            "total_reviews": total
        },
        "kpis": {
            "average_rating": avg_rating,
            "reputation_score": max(0, int(100 - risk_pct))
        },
        "visualizations": {
            "emotions": {
                e: round(sum(v)/len(v), 1) if v else 0
                for e, v in emotions_bucket.items()
            },
            "ratings": ratings_dist,
            "sentiment_trend": sentiment_trend
        },
        "risk": {
            "loss_probability": f"{risk_pct}%",
            "impact_level": (
                "Critical" if risk_pct > 40 else
                "High" if risk_pct > 25 else
                "Medium" if risk_pct > 12 else
                "Low"
            )
        }
    }

# ----------------------------------------------------------
# Endpoints
# ----------------------------------------------------------
@router.get("/health")
async def health():
    return {"status": "ok"}

# ✅ Frontend: /api/dashboard/ai/insights
@router.get("/ai/insights")
async def insights(
    company_id: int = Query(...),
    start: Optional[str] = None,
    end: Optional[str] = None,
    session: AsyncSession = Depends(get_db)
):
    start_dt, end_dt = safe_date(start), safe_date(end)
    stmt = select(Review).where(Review.company_id == company_id)
    if start_dt:
        stmt = stmt.where(Review.google_review_time >= start_dt)
    if end_dt:
        stmt = stmt.where(Review.google_review_time <= end_dt)

    reviews = (await session.execute(stmt)).scalars().all()
    return JSONResponse(compute_analytics(reviews))

# ✅ Frontend: /api/dashboard/revenue
@router.get("/revenue")
async def revenue(company_id: int, session: AsyncSession = Depends(get_db)):
    reviews = (await session.execute(
        select(Review).where(Review.company_id == company_id)
    )).scalars().all()
    analytics = compute_analytics(reviews)
    return {
        "risk_percent": analytics["risk"]["loss_probability"].replace("%", ""),
        "impact": analytics["risk"]["impact_level"]
    }

# ✅ Frontend: /api/dashboard/latest-reviews
@router.get("/latest-reviews")
async def latest_reviews(
    company_id: int,
    limit: int = 100,
    session: AsyncSession = Depends(get_db)
):
    rows = (await session.execute(
        select(Review)
        .where(Review.company_id == company_id)
        .order_by(desc(Review.google_review_time))
        .limit(limit)
    )).scalars().all()

    return [{
        "rating": r.rating,
        "sentiment": sentiment_label(r.rating),
        "review_text": r.text,
        "review_date": r.google_review_time.isoformat() if r.google_review_time else None,
        "source": "Google"
    } for r in rows]

# ✅ Frontend: /api/dashboard/chat
@router.post("/chat")
async def chat_ai(
    payload: Dict[str, str],
    company_id: int,
    session: AsyncSession = Depends(get_db)
):
    msg = payload.get("message", "").strip()
    company = await get_company(session, company_id)

    if not DEEPSEEK_API_KEY:
        return {"answer": "AI service not configured."}

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            DEEPSEEK_API_URL,
            headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}"},
            json={
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": f"You are a business consultant for {company.name}."},
                    {"role": "user", "content": msg}
                ],
                "temperature": 0.7,
                "max_tokens": 400
            }
        )
        return {"answer": r.json()["choices"][0]["message"]["content"]}

# ✅ Optional Executive PDF
@router.get("/executive-report/pdf/{company_id}")
async def pdf(company_id: int, session: AsyncSession = Depends(get_db)):
    company = await get_company(session, company_id)
    reviews = (await session.execute(
        select(Review).where(Review.company_id == company_id)
    )).scalars().all()

    analytics = compute_analytics(reviews)

    def build_pdf():
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", "B", 16)
        pdf.cell(0, 10, company.name, ln=True)
        pdf.set_font("Arial", "", 12)
        pdf.cell(0, 10, f"Avg Rating: {analytics['kpis']['average_rating']}", ln=True)
        pdf.cell(0, 10, f"Risk Level: {analytics['risk']['impact_level']}", ln=True)
        return pdf.output(dest="S")

    pdf_bytes = await asyncio.to_thread(build_pdf)
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=executive_report.pdf"}
    )
``
