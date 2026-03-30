# filename: app/routes/dashboard.py
from __future__ import annotations

import logging
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from fastapi.responses import JSONResponse
from sqlalchemy import and_, select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from app.core.db import get_session
from app.core.models import Company, Review

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])
logger = logging.getLogger(__name__)
analyzer = SentimentIntensityAnalyzer()

POS_THRESHOLD = 0.05
NEG_THRESHOLD = -0.05

# ---------------- HELPERS ----------------
def safe_date(val: Optional[str], default: datetime) -> datetime:
    """
    Parses an ISO-like string safely. Supports 'Z' suffix and naive strings.
    Falls back to the provided default if parsing fails.
    """
    try:
        if not val:
            return default
        # Replace Z with UTC offset for compatibility
        clean_val = val.replace("Z", "+00:00")
        d = datetime.fromisoformat(clean_val)
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return default

def sentiment_label(score: float) -> str:
    if score > POS_THRESHOLD:
        return "Positive"
    elif score < NEG_THRESHOLD:
        return "Negative"
    return "Neutral"

def detect_intent(question: str) -> str:
    q = (question or "").lower()
    if "rating" in q: return "rating"
    if "issue" in q or "problem" in q: return "issues"
    if "improve" in q or "better" in q: return "improve"
    if "good" in q or "strength" in q: return "strengths"
    return "general"

# ---------------- CORE ANALYSIS ----------------
async def analyze_company(
    session: AsyncSession, company_id: int, start_d: datetime, end_d: datetime
) -> Optional[Dict[str, Any]]:
    """
    Loads all reviews for a company in the date window.
    REFINED: Uses OR logic to ensure reviews are caught by scraped date OR sync date.
    """
    stmt = (
        select(Review)
        .where(
            Review.company_id == company_id,
            or_(
                and_(Review.google_review_time >= start_d, Review.google_review_time <= end_d),
                and_(Review.first_seen_at >= start_d, Review.first_seen_at <= end_d)
            )
        )
        .order_by(Review.first_seen_at.desc())
    )

    res = await session.execute(stmt)
    reviews = res.scalars().all()

    if not reviews:
        logger.info(f"No reviews found for company {company_id} in range {start_d} to {end_d}")
        return None

    sentiments: List[float] = []
    ratings: List[int] = []
    texts: List[str] = []
    monthly = defaultdict(list)

    for r in reviews:
        text = (r.text or "")
        score = analyzer.polarity_scores(text)["compound"]
        sentiments.append(score)
        ratings.append(r.rating if r.rating is not None else 0)
        texts.append(text)

        # Use whichever date is available for the chart mapping
        display_date = r.google_review_time or r.first_seen_at
        if display_date:
            key = display_date.strftime("%Y-%m")
            monthly[key].append(score)

    total_count = len(reviews)
    avg_rating = round(sum(ratings) / total_count, 2) if total_count else 0.0
    sentiment_avg = round(sum(sentiments) / total_count, 2) if total_count else 0.0

    monthly_data = [
        {"month": m, "sentiment": round(sum(v) / len(v), 2)}
        for m, v in sorted(monthly.items())
    ]

    return {
        "avg_rating": avg_rating,
        "sentiment": sentiment_avg,
        "total_reviews": total_count,
        "texts": texts,
        "monthly": monthly_data,
        "ratings": ratings,
        "sentiments": sentiments,
    }

async def get_dashboard_insights(
    session: AsyncSession, company_id: int, start_d: datetime, end_d: datetime
) -> Optional[Dict[str, Any]]:
    """
    Produces the exact payload used by /api/dashboard/insights.
    """
    data = await analyze_company(session, company_id, start_d, end_d)
    if not data:
        return None

    risk = round((1 - data["sentiment"]) * 100, 2)
    emotions = [
        "Happy" if s > 0.5 else "Angry" if s < -0.3 else "Neutral"
        for s in data["sentiments"]
    ]

    payload = {
        "kpis": {
            "rating": data["avg_rating"],
            "reviews": data["total_reviews"],
            "sentiment": data["sentiment"],
            "risk": risk,
        },
        "charts": {
            "monthly": data["monthly"],
            "emotions": dict(Counter(emotions)),
            "ratings": dict(Counter(data["ratings"])),
        },
    }
    return payload

# ---------------- DASHBOARD ----------------
@router.get("/insights")
async def dashboard(
    company_id: int,
    start: Optional[str] = None,
    end: Optional[str] = None,
    session: AsyncSession = Depends(get_session),
):
    # Defaulting to 1 year lookback to ensure Jan/Feb 2026 data is captured
    start_d = safe_date(start, datetime.now(timezone.utc) - timedelta(days=365))
    end_d = safe_date(end, datetime.now(timezone.utc))

    payload = await get_dashboard_insights(session, company_id, start_d, end_d)
    if not payload:
        return JSONResponse(content={"status": "no_data"}, status_code=200)

    return JSONResponse(content=payload)

# ---------------- AI CHATBOT ----------------
@router.post("/chat")
async def chatbot(
    company_id: int,
    question: str = Body(..., embed=True),
    session: AsyncSession = Depends(get_session),
):
    data = await analyze_company(
        session, company_id, 
        datetime.now(timezone.utc) - timedelta(days=365), 
        datetime.now(timezone.utc)
    )
    if not data: return {"answer": "No data available"}

    intent = detect_intent(question)
    words = " ".join(data["texts"]).lower().split()
    common = Counter([w for w in words if len(w) > 4]).most_common(6)
    issues = [w for w, _ in common[:3]]
    strengths = [w for w, _ in common[3:]]

    if intent == "rating":
        answer = f"Your average rating is {data['avg_rating']}. Drivers include {', '.join(issues)}."
    elif intent == "issues":
        answer = f"Identified concerns: {', '.join(issues)}."
    elif intent == "strengths":
        answer = f"Strengths: {', '.join(strengths)}."
    elif intent == "improve":
        answer = f"To improve, focus on {', '.join(issues)}."
    else:
        answer = f"Overview: Rating {data['avg_rating']} across {data['total_reviews']} reviews."

    return {"answer": answer}

# ---------------- COMPETITOR BENCHMARK ----------------
@router.post("/compare")
async def compare(
    company_ids: List[int] = Body(...),
    session: AsyncSession = Depends(get_session),
):
    results = []
    for cid in company_ids:
        data = await analyze_company(
            session, cid, 
            datetime.now(timezone.utc) - timedelta(days=365), 
            datetime.now(timezone.utc)
        )
        if data:
            results.append({
                "company_id": cid,
                "rating": data["avg_rating"],
                "reviews": data["total_reviews"],
            })
    return {"comparison": results}

# ---------------- REVENUE & RISK ----------------
@router.get("/revenue")
async def revenue(company_id: int, session: AsyncSession = Depends(get_session)):
    data = await analyze_company(
        session, company_id, 
        datetime.now(timezone.utc) - timedelta(days=365), 
        datetime.now(timezone.utc)
    )
    if not data: return {"status": "no_data"}
    risk = (1 - data["sentiment"]) * 100
    return {
        "risk_percent": round(risk, 2),
        "impact": "HIGH" if risk > 50 else "MEDIUM" if risk > 25 else "LOW",
    }

# ---------------- AUTO REPLY ----------------
@router.post("/reply")
async def reply(review_text: str = Body(..., embed=True)):
    score = analyzer.polarity_scores(review_text)["compound"]
    if score > 0:
        return {"reply": "Thank you for your kind words! We are thrilled you enjoyed your experience."}
    return {"reply": "We are sorry to hear about your experience. Please reach out so we can make this right."}
