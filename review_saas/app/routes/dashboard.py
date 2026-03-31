# ===================================================================
# PROJECT: ReviewSaaS - AI Intelligence Dashboard
# FULLY INTEGRATED VERSION (FRONTEND + POSTGRESQL)
# ===================================================================

from __future__ import annotations
import logging
import re
from io import BytesIO
from collections import defaultdict, Counter
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse, StreamingResponse

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from app.core.db import get_session
from app.core.models import Review

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import LETTER

# -------------------------------------------------------------------
# INIT
# -------------------------------------------------------------------

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("dashboard")

# -------------------------------------------------------------------
# HELPERS
# -------------------------------------------------------------------

def safe_avg(values: List[float]) -> float:
    return round(sum(values) / len(values), 2) if values else 0.0


def parse_date(val: Optional[str]) -> Optional[datetime]:
    if not val:
        return None
    try:
        return datetime.fromisoformat(val.replace("Z", "+00:00"))
    except:
        return None


# -------------------------------------------------------------------
# ANALYTICS ENGINE
# -------------------------------------------------------------------

class Engine:

    @staticmethod
    def nps(reviews: List[Review]) -> int:
        total = len(reviews)
        if total == 0:
            return 0

        promoters = len([r for r in reviews if (r.rating or 0) >= 4])
        detractors = len([r for r in reviews if (r.rating or 0) <= 2])

        return int(((promoters - detractors) / total) * 100)

    @staticmethod
    def keywords(reviews: List[Review]) -> List[Dict[str, Any]]:
        text = " ".join([(r.text or "").lower() for r in reviews])
        words = re.findall(r"\b[a-z]{4,}\b", text)

        stop = {"this","that","with","have","were","from","they","their","about"}
        words = [w for w in words if w not in stop]

        return [{"text": k, "value": v} for k, v in Counter(words).most_common(12)]

    @staticmethod
    def visuals(reviews: List[Review]) -> Dict[str, Any]:

        ratings = {i: 0 for i in range(1, 6)}
        emotions = {"Positive": 0, "Neutral": 0, "Negative": 0}
        trend_map = defaultdict(list)

        for r in reviews:

            # ratings
            if r.rating and 1 <= int(r.rating) <= 5:
                ratings[int(r.rating)] += 1

            # sentiment
            s = r.sentiment_score or 0
            if s >= 0.25:
                emotions["Positive"] += 1
            elif s <= -0.25:
                emotions["Negative"] += 1
            else:
                emotions["Neutral"] += 1

            # trend
            t = r.google_review_time or getattr(r, "first_seen_at", None)
            if t:
                key = t.strftime("%b %d")
                trend_map[key].append(r.rating or 0)

        trend = [
            {"week": k, "avg": safe_avg(v)}
            for k, v in sorted(trend_map.items())
        ]

        return {
            "ratings": ratings,
            "emotions": emotions,
            "sentiment_trend": trend,
            "keywords": Engine.keywords(reviews)
        }


# -------------------------------------------------------------------
# MAIN ENDPOINT (AUTO FRONTEND TRIGGER)
# -------------------------------------------------------------------

@router.get("/ai/insights")
async def insights(
    company_id: int = Query(...),

    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),

    amp_start: Optional[str] = Query(None, alias="amp;start"),
    amp_end: Optional[str] = Query(None, alias="amp;end"),

    session: AsyncSession = Depends(get_session)
):

    # Fix frontend broken params
    start_val = start or amp_start
    end_val = end or amp_end

    s_dt = parse_date(start_val)
    e_dt = parse_date(end_val)

    stmt = select(Review).where(Review.company_id == company_id)

    if s_dt and e_dt:
        stmt = stmt.where(and_(
            Review.google_review_time >= s_dt,
            Review.google_review_time <= e_dt
        ))

    result = await session.execute(stmt)
    reviews = result.scalars().all()

    # -------- EMPTY SAFE --------
    if not reviews:
        return _empty()

    # -------- KPIs --------
    ratings_list = [r.rating for r in reviews if r.rating]
    avg_rating = safe_avg(ratings_list)
    reputation = Engine.nps(reviews)

    visuals = Engine.visuals(reviews)

    return {
        "metadata": {
            "total_reviews": len(reviews),
            "last_updated": datetime.now(timezone.utc).isoformat()
        },
        "kpis": {
            "average_rating": avg_rating,
            "reputation_score": reputation
        },
        "visualizations": visuals
    }


# -------------------------------------------------------------------
# REVENUE
# -------------------------------------------------------------------

@router.get("/revenue")
async def revenue(
    company_id: int = Query(...),
    session: AsyncSession = Depends(get_session)
):
    result = await session.execute(
        select(func.avg(Review.rating)).where(Review.company_id == company_id)
    )
    avg = result.scalar() or 0

    if avg >= 4.5:
        return {"risk_percent": 5, "impact": "Negligible"}
    elif avg >= 4:
        return {"risk_percent": 15, "impact": "Low"}
    elif avg >= 3:
        return {"risk_percent": 45, "impact": "Medium"}
    else:
        return {"risk_percent": 85, "impact": "High"}


# -------------------------------------------------------------------
# CHATBOT
# -------------------------------------------------------------------

@router.get("/chatbot/explain/{company_id}")
async def chat(
    company_id: int,
    question: str,
    session: AsyncSession = Depends(get_session)
):
    result = await session.execute(
        select(func.avg(Review.rating), func.count(Review.id))
        .where(Review.company_id == company_id)
    )

    avg, count = result.first()

    q = question.lower()

    if "improve" in q:
        ans = "Focus on negative reviews and respond within 24 hours."
    elif "trend" in q:
        ans = "Trend shows fluctuations — consistency is key."
    elif "risk" in q:
        ans = f"Current rating {round(avg or 0,2)} indicates moderate risk."
    else:
        ans = f"Based on {count} reviews, performance is stable."

    return {"answer": ans}


# -------------------------------------------------------------------
# PDF REPORT
# -------------------------------------------------------------------

@router.get("/executive-report/pdf/{company_id}")
async def pdf(
    company_id: int,
    session: AsyncSession = Depends(get_session)
):

    result = await session.execute(
        select(func.avg(Review.rating), func.count(Review.id))
        .where(Review.company_id == company_id)
    )

    avg, count = result.first()

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=LETTER)

    pdf.drawString(50, 750, "Executive Report")
    pdf.drawString(50, 720, f"Company ID: {company_id}")
    pdf.drawString(50, 690, f"Avg Rating: {round(avg or 0,2)}")
    pdf.drawString(50, 660, f"Total Reviews: {count or 0}")

    pdf.save()
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=report.pdf"}
    )


# -------------------------------------------------------------------
# EMPTY SAFE RESPONSE
# -------------------------------------------------------------------

def _empty():
    return JSONResponse({
        "metadata": {"total_reviews": 0},
        "kpis": {"average_rating": 0, "reputation_score": 0},
        "visualizations": {
            "ratings": {i: 0 for i in range(1, 6)},
            "emotions": {"Positive": 0, "Neutral": 0, "Negative": 0},
            "sentiment_trend": [],
            "keywords": []
        }
    })
