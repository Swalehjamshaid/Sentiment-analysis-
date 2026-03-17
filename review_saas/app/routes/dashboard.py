# filename: app/routes/dashboard.py
from __future__ import annotations
import logging
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from fastapi.responses import JSONResponse
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from app.core.db import get_session
from app.core.models import Company, Review
from app.services.scraper import FastGoogleScraper

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])
logger = logging.getLogger(__name__)
analyzer = SentimentIntensityAnalyzer()
scraper = FastGoogleScraper()

POS_THRESHOLD = 0.05
NEG_THRESHOLD = -0.05

# ---------------- HELPERS ----------------
def safe_date(val, default):
    try:
        if not val:
            return default
        d = datetime.fromisoformat(val.replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except:
        return default

def sentiment_label(score):
    if score > POS_THRESHOLD:
        return "Positive"
    elif score < NEG_THRESHOLD:
        return "Negative"
    return "Neutral"

def detect_intent(question: str):
    q = question.lower()
    if "rating" in q:
        return "rating"
    if "issue" in q or "problem" in q:
        return "issues"
    if "improve" in q or "better" in q:
        return "improve"
    if "good" in q or "strength" in q:
        return "strengths"
    return "general"

# ---------------- CORE ANALYSIS ----------------
async def analyze_company(session, company_id, start_d, end_d):
    stmt = select(Review).where(
        and_(
            Review.company_id == company_id,
            Review.google_review_time >= start_d,
            Review.google_review_time <= end_d
        )
    ).order_by(Review.google_review_time.desc()).limit(100)  # last 100 reviews
    res = await session.execute(stmt)
    reviews = res.scalars().all()

    if not reviews:
        return None

    sentiments, ratings, texts = [], [], []
    monthly = defaultdict(list)

    for r in reviews:
        text = (r.text or "")
        score = analyzer.polarity_scores(text)["compound"]
        sentiments.append(score)
        ratings.append(r.rating)
        texts.append(text)

        if r.google_review_time:
            key = r.google_review_time.strftime("%Y-%m")
            monthly[key].append(score)

    avg_rating = round(sum(ratings) / len(ratings), 2)
    sentiment_avg = round(sum(sentiments) / len(sentiments), 2)
    monthly_data = [
        {"month": m, "sentiment": round(sum(v)/len(v), 2)}
        for m, v in sorted(monthly.items())
    ]

    return {
        "avg_rating": avg_rating,
        "sentiment": sentiment_avg,
        "total_reviews": len(reviews),
        "texts": texts[:300],
        "monthly": monthly_data,
        "ratings": ratings,
        "sentiments": sentiments
    }

# ---------------- DASHBOARD ----------------
@router.get("/insights")
async def dashboard(
    company_id: int,
    start: Optional[str] = None,
    end: Optional[str] = None,
    session: AsyncSession = Depends(get_session)
):
    start_d = safe_date(start, datetime.now(timezone.utc) - timedelta(days=365))
    end_d = safe_date(end, datetime.now(timezone.utc))

    data = await analyze_company(session, company_id, start_d, end_d)
    if not data:
        return {"status": "no_data"}

    risk = round((1 - data["sentiment"]) * 100, 2)
    emotions = [
        "Happy" if s > 0.5 else "Angry" if s < -0.3 else "Neutral"
        for s in data["sentiments"]
    ]

    return JSONResponse(content={
        "kpis": {
            "rating": data["avg_rating"],
            "reviews": data["total_reviews"],
            "sentiment": data["sentiment"],
            "risk": risk
        },
        "charts": {
            "monthly": data["monthly"],
            "emotions": dict(Counter(emotions)),
            "ratings": dict(Counter(data["ratings"]))
        }
    })

# ---------------- AI CHATBOT ----------------
@router.post("/chat")
async def chatbot(
    company_id: int,
    question: str = Body(...),
    session: AsyncSession = Depends(get_session)
):
    data = await analyze_company(
        session,
        company_id,
        datetime.now(timezone.utc) - timedelta(days=365),
        datetime.now(timezone.utc)
    )
    if not data:
        return {"answer": "No data available"}

    intent = detect_intent(question)
    words = " ".join(data["texts"]).lower().split()
    common = Counter([w for w in words if len(w) > 4]).most_common(6)
    issues = [w for w, _ in common[:3]]
    strengths = [w for w, _ in common[3:]]

    if intent == "rating":
        answer = f"Your rating is {data['avg_rating']}. Main issues: {', '.join(issues)}"
    elif intent == "issues":
        answer = f"Top issues: {', '.join(issues)}"
    elif intent == "strengths":
        answer = f"Strengths: {', '.join(strengths)}"
    elif intent == "improve":
        answer = f"Improve by fixing: {', '.join(issues)} and focusing on customer experience."
    else:
        answer = f"Rating: {data['avg_rating']}, Reviews: {data['total_reviews']}"

    return {"answer": answer}

# ---------------- COMPETITOR BENCHMARK ----------------
@router.post("/compare")
async def compare(
    company_ids: List[int] = Body(...),
    session: AsyncSession = Depends(get_session)
):
    results = []
    for cid in company_ids:
        data = await analyze_company(
            session,
            cid,
            datetime.now(timezone.utc) - timedelta(days=365),
            datetime.now(timezone.utc)
        )
        if data:
            results.append({
                "company_id": cid,
                "rating": data["avg_rating"],
                "reviews": data["total_reviews"]
            })
    return {"comparison": results}

# ---------------- REVENUE & RISK ----------------
@router.get("/revenue")
async def revenue(company_id: int, session: AsyncSession = Depends(get_session)):
    data = await analyze_company(
        session,
        company_id,
        datetime.now(timezone.utc) - timedelta(days=365),
        datetime.now(timezone.utc)
    )
    if not data:
        return {"status": "no_data"}
    risk = (1 - data["sentiment"]) * 100
    return {
        "risk_percent": round(risk, 2),
        "impact": "HIGH" if risk > 50 else "MEDIUM" if risk > 25 else "LOW"
    }

# ---------------- AUTO REPLY ----------------
@router.post("/reply")
async def reply(review_text: str = Body(...)):
    score = analyzer.polarity_scores(review_text)["compound"]
    if score > 0:
        return {"reply": "Thank you for your positive feedback!"}
    else:
        return {"reply": "We apologize and will improve your experience."}
