# filename: app/routes/dashboard.py
# ==========================================================
# REVIEW INTELLIGENCE DASHBOARD — ENTERPRISE FINAL (NO LOSS)
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
from sqlalchemy import select, desc

from fpdf import FPDF
import openai

from app.core.db import get_session
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


def sanitize_pdf(text: str) -> str:
    """
    Makes text 100% safe for FPDF (latin-1 only).
    Prevents UnicodeEncodeError permanently.
    """
    replacements = {
        "—": "-",
        "–": "-",
        "’": "'",
        "“": '"',
        "”": '"',
        "•": "-",
        "…": "..."
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
    return text.encode("latin-1", "ignore").decode("latin-1")


def clean_keywords(text: str) -> List[str]:
    words = []
    for w in text.lower().split():
        w = w.strip(".,!?()")
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
# ✅ CORE ANALYTICS ENGINE (SINGLE SOURCE OF TRUTH)
# ----------------------------------------------------------
def compute_analytics(reviews: List[Review]) -> Dict:
    """
    All KPIs, trends, risk & AI must use THIS.
    This prevents KPI mismatch anywhere in the system.
    """

    if not reviews:
        return {
            "total_reviews": 0,
            "average_rating": 0,
            "sentiment_counts": {"Positive": 0, "Neutral": 0, "Negative": 0},
            "rating_distribution": {i: 0 for i in range(1, 6)},
            "monthly_trend": [],
            "risk": {
                "loss_probability": "0%",
                "impact_level": "None",
                "reputation_score": 100
            }
        }

    ratings: List[int] = []
    sentiments: List[float] = []
    monthly_map: Dict[str, List[int]] = defaultdict(list)

    sentiment_counts = {"Positive": 0, "Neutral": 0, "Negative": 0}
    rating_distribution = {i: 0 for i in range(1, 6)}

    severe_count = 0
    negative_count = 0

    for r in reviews:
        if r.rating:
            rating_distribution[int(r.rating)] += 1
            ratings.append(int(r.rating))

            if r.google_review_time:
                key = r.google_review_time.strftime("%b %Y")
                monthly_map[key].append(int(r.rating))

            if r.rating in NEGATIVE_RATINGS:
                severe_count += 1

        if r.sentiment_score is not None:
            sentiments.append(r.sentiment_score)

            if r.sentiment_score <= NEG_SENTIMENT_LIMIT:
                sentiment_counts["Negative"] += 1
                negative_count += 1
            elif r.sentiment_score >= abs(NEG_SENTIMENT_LIMIT):
                sentiment_counts["Positive"] += 1
            else:
                sentiment_counts["Neutral"] += 1

    avg_rating = round(sum(ratings) / len(ratings), 2)
    avg_sentiment = round(sum(sentiments) / len(sentiments), 2) if sentiments else 0

    # Risk model (weighted, stable, explainable)
    raw_risk = (negative_count * 0.6 + severe_count * 0.4) / len(reviews)
    risk_pct = round(raw_risk * 100, 1)

    return {
        "total_reviews": len(reviews),
        "average_rating": avg_rating,
        "sentiment_counts": sentiment_counts,
        "rating_distribution": rating_distribution,
        "monthly_trend": [
            {
                "month": k,
                "avg": round(sum(v) / len(v), 2),
                "count": len(v)
            }
            for k, v in sorted(monthly_map.items())
        ],
        "risk": {
            "loss_probability": f"{risk_pct}%",
            "impact_level": (
                "High" if risk_pct > 25
                else "Medium" if risk_pct > 12
                else "Low"
            ),
            "reputation_score": max(0, round(100 - risk_pct, 1))
        }
    }

# ==========================================================
# 1. OVERVIEW (KPI CARDS)
# ==========================================================
@router.get("/overview/{company_id}", response_class=JSONResponse)
async def overview(company_id: int, session: AsyncSession = Depends(get_session)):
    await get_company(session, company_id)

    res = await session.execute(
        select(Review).where(Review.company_id == company_id)
    )
    analytics = compute_analytics(res.scalars().all())

    return {
        "total_reviews": analytics["total_reviews"],
        "average_rating": analytics["average_rating"]
    }

# ==========================================================
# 2. INSIGHTS (CHARTS + KEYWORDS)
# ==========================================================
@router.get("/insights", response_class=JSONResponse)
async def insights(
    company_id: int = Query(...),
    start: str | None = Query(None),
    end: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
):
    await get_company(session, company_id)

    stmt = select(Review).where(Review.company_id == company_id)

    start_dt = safe_date(start)
    end_dt = safe_date(end)
    if start_dt:
        stmt = stmt.where(Review.google_review_time >= start_dt)
    if end_dt:
        stmt = stmt.where(Review.google_review_time <= end_dt)

    res = await session.execute(stmt)
    reviews = res.scalars().all()

    analytics = compute_analytics(reviews)

    keywords: List[str] = []
    for r in reviews:
        if r.text:
            keywords.extend(clean_keywords(r.text))

    analytics["top_keywords"] = [
        w for w, _ in Counter(keywords).most_common(20)
    ]

    return analytics

# ==========================================================
# 3. REVENUE RISK (USED BY FRONTEND)
# ==========================================================
@router.get("/revenue", response_class=JSONResponse)
async def revenue(company_id: int, session: AsyncSession = Depends(get_session)):
    await get_company(session, company_id)

    res = await session.execute(
        select(Review).where(Review.company_id == company_id)
    )
    analytics = compute_analytics(res.scalars().all())

    return analytics["risk"]

# ==========================================================
# 4. AI CHATBOT (EXECUTIVE‑GRADE)
# ==========================================================
@router.post("/chatbot/explain", response_class=JSONResponse)
async def chatbot(
    question: str = Query(...),
    company_id: int = Query(...),
    session: AsyncSession = Depends(get_session)
):
    res = await session.execute(
        select(Review).where(Review.company_id == company_id).limit(200)
    )
    reviews = res.scalars().all()
    analytics = compute_analytics(reviews)

    prompt = f"""
You are a senior business strategy consultant.

Business KPIs:
- Total Reviews: {analytics['total_reviews']}
- Average Rating: {analytics['average_rating']}
- Loss Probability: {analytics['risk']['loss_probability']}
- Impact Level: {analytics['risk']['impact_level']}
- Reputation Score: {analytics['risk']['reputation_score']}

Monthly Rating Trend:
{analytics['monthly_trend']}

Question:
{question}

Provide clear, data‑driven, actionable insights.
"""

    try:
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
# 5. AI EXECUTIVE SUMMARY (TEXT)
# ==========================================================
@router.get("/ai-summary/{company_id}")
async def ai_summary(company_id: int, session: AsyncSession = Depends(get_session)):
    await get_company(session, company_id)

    res = await session.execute(
        select(Review).where(Review.company_id == company_id)
    )
    analytics = compute_analytics(res.scalars().all())

    if analytics["total_reviews"] == 0:
        return {"summary": "No sufficient data available."}

    summary = f"""
Business Performance Summary:

- Average Rating: {analytics['average_rating']}
- Loss Probability: {analytics['risk']['loss_probability']}
- Reputation Score: {analytics['risk']['reputation_score']}

Key Insight:
Customer sentiment is {analytics['risk']['impact_level'].lower()} risk.

Recommendations:
- Address negative reviews proactively
- Strengthen high-performing service areas
"""

    return {"summary": summary.strip()}

# ==========================================================
# 6. EXECUTIVE PDF REPORT (SAFE)
# ==========================================================
@router.get("/executive-report/pdf/{company_id}")
async def executive_report(company_id: int, session: AsyncSession = Depends(get_session)):
    company = await get_company(session, company_id)

    res = await session.execute(
        select(Review).where(Review.company_id == company_id)
    )
    analytics = compute_analytics(res.scalars().all())

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 16)

    pdf.cell(
        0, 10,
        sanitize_pdf(f"Executive Report - {company.name}"),
        ln=True, align="C"
    )
    pdf.ln(8)

    pdf.set_font("Arial", size=12)
    pdf.cell(0, 8, f"Total Reviews: {analytics['total_reviews']}", ln=True)
    pdf.cell(0, 8, f"Average Rating: {analytics['average_rating']}", ln=True)
    pdf.cell(0, 8, f"Loss Probability: {analytics['risk']['loss_probability']}", ln=True)
    pdf.cell(0, 8, f"Impact Level: {analytics['risk']['impact_level']}", ln=True)
    pdf.cell(0, 8, f"Reputation Score: {analytics['risk']['reputation_score']}", ln=True)
    pdf.cell(
        0, 8,
        f"Generated On: {datetime.utcnow().strftime('%Y-%m-%d')}",
        ln=True
    )

    buffer = io.BytesIO(pdf.output(dest="S").encode("latin-1"))
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={
            "Content-Disposition":
            f"attachment; filename=Executive_Report_{company_id}.pdf"
        }
    )

# ==========================================================
# 7. RECENT REVIEWS
# ==========================================================
@router.get("/recent-reviews/{company_id}", response_class=JSONResponse)
async def get_recent_reviews(company_id: int, session: AsyncSession = Depends(get_session)):
    await get_company(session, company_id)

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

    return [
        {
            "author": r.author_name,
            "rating": r.rating,
            "text": r.text,
            "date": (
                r.google_review_time.strftime("%Y-%m-%d")
                if r.google_review_time else "N/A"
            )
        }
        for r in res.fetchall()
    ]
