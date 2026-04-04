from __future__ import annotations
import io
import os
import logging
from datetime import datetime
from collections import Counter, defaultdict
from typing import Dict, List, Any

from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from fpdf import FPDF
import openai

# ✅ FIXED IMPORT (NO I/O CHANGE)
from app.core.db import get_db
from app.core.models import Company, Review

# ----------------------------------------------------------
# Configuration
# ----------------------------------------------------------
router = APIRouter(prefix="", tags=["Dashboard"])
logger = logging.getLogger("dashboard")
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

# ----------------------------------------------------------
# CORE ANALYTICS ENGINE
# ----------------------------------------------------------
def compute_analytics(reviews: List[Review]) -> Dict[str, Any]:
    if not reviews:
        return {
            "total_reviews": 0,
            "average_rating": 0.0,
            "sentiment_counts": {"Positive": 0, "Neutral": 0, "Negative": 0},
            "rating_distribution": {i: 0 for i in range(1, 6)},
            "monthly_trend": [],
            "risk": {"loss_probability": "0%", "impact_level": "None", "reputation_score": 100.0},
            "negative_reviews": [],
            "churn_prediction": 0.0,
            "loyalty_score": 0.0
        }

    ratings = []
    monthly_map = defaultdict(list)
    sentiment_counts = {"Positive": 0, "Neutral": 0, "Negative": 0}
    rating_distribution = {i: 0 for i in range(1, 6)}
    severe_count = negative_count = 0
    negative_reviews = []

    for r in reviews:
        if r.rating:
            rating_distribution[int(r.rating)] += 1
            ratings.append(int(r.rating))
            if r.google_review_time:
                monthly_map[r.google_review_time.strftime("%b %Y")].append(int(r.rating))
            if r.rating in NEGATIVE_RATINGS:
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
    risk_pct = round(((negative_count * 0.6 + severe_count * 0.4) / total) * 100, 1) if total else 0

    return {
        "total_reviews": total,
        "average_rating": avg_rating,
        "sentiment_counts": sentiment_counts,
        "rating_distribution": rating_distribution,
        "monthly_trend": [{"month": k, "avg": round(sum(v)/len(v), 2), "count": len(v)} for k, v in monthly_map.items()],
        "risk": {
            "loss_probability": f"{risk_pct}%",
            "impact_level": "High" if risk_pct > 25 else "Medium" if risk_pct > 12 else "Low",
            "reputation_score": max(0.0, round(100 - risk_pct, 1))
        },
        "negative_reviews": negative_reviews,
        "churn_prediction": round(risk_pct * 0.9, 1),
        "loyalty_score": round((sentiment_counts["Positive"] / total) * 100, 1) if total else 0
    }

# ----------------------------------------------------------
# ROUTES (UNCHANGED I/O)
# ----------------------------------------------------------
@router.get("/overview/{company_id}", response_class=JSONResponse)
async def overview(company_id: int, session: AsyncSession = Depends(get_db)):
    await get_company(session, company_id)
    res = await session.execute(select(Review).where(Review.company_id == company_id))
    analytics = compute_analytics(res.scalars().all())
    return {
        "total_reviews": analytics["total_reviews"],
        "average_rating": analytics["average_rating"],
    }
