# filename: app/routes/dashboard.py
# ==========================================================
# REVIEW INTELLIGENCE DASHBOARD — FINAL 100% FIXED VERSION
# ==========================================================

from __future__ import annotations

import io
import os
import logging
import asyncio
from datetime import datetime
from collections import Counter, defaultdict
from typing import Dict, List, Any, Optional

from fastapi import APIRouter, Depends, Query, HTTPException, Body
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
router = APIRouter(prefix="/api", tags=["Dashboard"])
logger = logging.getLogger("dashboard")

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

NEGATIVE_RATINGS = {1, 2}
NEG_SENTIMENT_LIMIT = -0.2
MAX_FETCH = 3000  # prevent memory overload

STOPWORDS = {
    "the","and","with","this","that","for","from","was","were",
    "have","has","had","very","just","they","them","their","there",
    "but","not","are","you","your","will","can","our","all","any"
}

# ----------------------------------------------------------
# HELPERS
# ----------------------------------------------------------
def safe_date(val: Optional[str]) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(val) if val else None
    except:
        return None


def sanitize_pdf(text: str) -> str:
    return text.replace("—", "-").replace("’", "'")


def clean_keywords(text: str) -> List[str]:
    if not text:
        return []
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
        raise HTTPException(404, "Company not found")
    return company

# ----------------------------------------------------------
# CORE ANALYTICS (100% FRONTEND MATCH)
# ----------------------------------------------------------
def compute_analytics(reviews: List[Review]) -> Dict[str, Any]:

    if not reviews:
        return {
            "metadata": {"total_reviews": 0},
            "kpis": {
                "average_rating": 0,
                "churn_prediction": 0,
                "loyalty_score": 0,
                "reputation_score": 100
            },
            "visualizations": {
                "emotions": {"Positive": 0, "Neutral": 0, "Negative": 0},
                "ratings": {i: 0 for i in range(1, 6)},
                "sentiment_trend": []
            },
            "risk": {
                "loss_probability": "0%",
                "impact_level": "Low"
            }
        }

    ratings = []
    sentiment = {"Positive": 0, "Neutral": 0, "Negative": 0}
    rating_dist = {i: 0 for i in range(1, 6)}
    monthly = defaultdict(list)

    neg = 0
    severe = 0

    for r in reviews:

        if r.rating:
            rating = int(r.rating)
            ratings.append(rating)
            rating_dist[rating] += 1

            if rating in NEGATIVE_RATINGS:
                severe += 1

        if r.sentiment_score is not None:
            if r.sentiment_score <= NEG_SENTIMENT_LIMIT:
                sentiment["Negative"] += 1
                neg += 1
            elif r.sentiment_score >= abs(NEG_SENTIMENT_LIMIT):
                sentiment["Positive"] += 1
            else:
                sentiment["Neutral"] += 1

        if r.google_review_time and r.rating:
            key = r.google_review_time.strftime("%b %Y")
            monthly[key].append(r.rating)

    total = len(reviews)
    avg = round(sum(ratings)/len(ratings), 2) if ratings else 0

    risk_pct = round(((neg*0.6 + severe*0.4)/total)*100, 1)

    trend = sorted([
        {"month": k, "avg": round(sum(v)/len(v), 2)}
        for k,v in monthly.items()
    ], key=lambda x: datetime.strptime(x["month"], "%b %Y"))

    return {
        "metadata": {"total_reviews": total},
        "kpis": {
            "average_rating": avg,
            "churn_prediction": round((neg/total)*100,1),
            "loyalty_score": round((sentiment["Positive"]/total)*100,1),
            "reputation_score": max(0, 100-risk_pct)
        },
        "visualizations": {
            "emotions": sentiment,
            "ratings": rating_dist,
            "sentiment_trend": trend
        },
        "risk": {
            "loss_probability": f"{risk_pct}%",
            "impact_level": "High" if risk_pct>25 else "Medium" if risk_pct>12 else "Low"
        }
    }

# ----------------------------------------------------------
# ROUTES (FULLY ALIGNED)
# ----------------------------------------------------------
@router.get("/insights")
async def insights(
    company_id: int,
    start: Optional[str] = None,
    end: Optional[str] = None,
    session: AsyncSession = Depends(get_db)
):

    await get_company(session, company_id)

    stmt = select(Review).where(Review.company_id == company_id)

    if start_dt := safe_date(start):
        stmt = stmt.where(
            (Review.google_review_time != None) &
            (Review.google_review_time >= start_dt)
        )

    if end_dt := safe_date(end):
        stmt = stmt.where(
            (Review.google_review_time != None) &
            (Review.google_review_time <= end_dt)
        )

    stmt = stmt.limit(MAX_FETCH)

    res = await session.execute(stmt)
    reviews = res.scalars().all()

    analytics = compute_analytics(reviews)

    keywords = []
    for r in reviews:
        keywords.extend(clean_keywords(r.text))

    analytics["top_keywords"] = [
        w for w,_ in Counter(keywords).most_common(20)
    ]

    return analytics


@router.get("/revenue")
async def revenue(company_id: int, session: AsyncSession = Depends(get_db)):

    await get_company(session, company_id)

    res = await session.execute(
        select(Review).where(Review.company_id == company_id).limit(MAX_FETCH)
    )

    analytics = compute_analytics(res.scalars().all())

    risk_pct = float(analytics["risk"]["loss_probability"].replace("%",""))

    return {
        "risk_percent": risk_pct,
        "impact": analytics["risk"]["impact_level"],
        "reputation_score": analytics["kpis"]["reputation_score"]
    }


@router.post("/chatbot/explain")
async def chatbot(
    company_id: int = Query(...),
    body: dict = Body(...),
    session: AsyncSession = Depends(get_db)
):

    question = body.get("message")

    if not question:
        raise HTTPException(400, "Message required")

    res = await session.execute(
        select(Review).where(Review.company_id == company_id).limit(300)
    )

    analytics = compute_analytics(res.scalars().all())

    prompt = f"""
Business:
Reviews: {analytics['metadata']['total_reviews']}
Rating: {analytics['kpis']['average_rating']}
Risk: {analytics['risk']['loss_probability']}

Question: {question}
"""

    try:
        response = await asyncio.to_thread(
            lambda: client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role":"user","content":prompt}],
                temperature=0.3
            )
        )

        return {"answer": response.choices[0].message.content}

    except Exception as e:
        logger.error(e)
        return {"answer":"AI unavailable"}


@router.get("/recent-reviews/{company_id}")
async def recent_reviews(company_id:int, session: AsyncSession = Depends(get_db)):

    await get_company(session, company_id)

    res = await session.execute(
        select(Review)
        .where(Review.company_id==company_id)
        .order_by(desc(Review.google_review_time))
        .limit(100)
    )

    return [
        {
            "author": r.author_name or "Anonymous",
            "rating": r.rating or 0,
            "text": r.text or "",
            "date": r.google_review_time.strftime("%Y-%m-%d") if r.google_review_time else "N/A"
        }
        for r in res.scalars()
    ]
