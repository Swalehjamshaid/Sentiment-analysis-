# filename: app/routes/dashboard.py

from __future__ import annotations
import logging
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, Body
from fastapi.responses import JSONResponse
from sqlalchemy import and_, select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from app.core.db import get_session
from app.core.models import Company, Review

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])

logger = logging.getLogger(__name__)
analyzer = SentimentIntensityAnalyzer()

POS_THRESHOLD = 0.05
NEG_THRESHOLD = -0.05

# ---------------- HELPER FUNCTIONS ----------------

def safe_date(val, default):
    try:
        if not val:
            return default
        d = datetime.fromisoformat(val.replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
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

def aggregate_monthly_data(reviews: List[Review]):
    monthly = defaultdict(list)
    for r in reviews:
        if r.google_review_time:
            key = r.google_review_time.strftime("%Y-%m")
            score = analyzer.polarity_scores(r.text or "")["compound"]
            monthly[key].append(score)
    return [
        {"month": m, "sentiment": round(sum(v)/len(v), 2), "volume": len(v)}
        for m, v in sorted(monthly.items())
    ]

def compute_ai_growth_score(data):
    if not data or data["total_reviews"] == 0:
        return 0
    avg_rating = data["avg_rating"] / 5
    sentiment_score = (data["sentiment"] + 1) / 2
    review_growth = sum([v["volume"] for v in data["monthly"][-3:]]) / max(data["total_reviews"], 1)
    rating_stability = 1 - (max(data["ratings"]) - min(data["ratings"])) / 5
    score = (0.4*avg_rating + 0.3*sentiment_score + 0.2*review_growth + 0.1*rating_stability) * 100
    return round(score, 2)

# ---------------- CORE ANALYSIS ----------------

async def analyze_company(session: AsyncSession, company_id: int, start_d, end_d):
    stmt = select(Review).where(
        and_(
            Review.company_id == company_id,
            Review.google_review_time >= start_d,
            Review.google_review_time <= end_d
        )
    ).order_by(desc(Review.google_review_time)).limit(100)  # last 100 reviews
    res = await session.execute(stmt)
    reviews = res.scalars().all()
    if not reviews:
        return None

    sentiments, ratings, texts = [], [], []
    for r in reviews:
        score = analyzer.polarity_scores(r.text or "")["compound"]
        sentiments.append(score)
        ratings.append(r.rating)
        texts.append(r.text or "")

    avg_rating = round(sum(ratings)/len(ratings), 2)
    sentiment_avg = round(sum(sentiments)/len(sentiments), 2)
    monthly_data = aggregate_monthly_data(reviews)

    words = [w.lower() for t in texts for w in t.split() if len(w) > 4]
    word_counts = Counter(words)
    top_issues = [w for w, _ in word_counts.most_common(5)]
    top_strengths = [w for w, _ in word_counts.most_common()[-5:]]

    review_velocity = {m["month"]: m["volume"] for m in monthly_data}
    rating_distribution = dict(Counter(ratings))
    ai_growth_score = compute_ai_growth_score({
        "avg_rating": avg_rating,
        "sentiment": sentiment_avg,
        "monthly": monthly_data,
        "ratings": ratings,
        "total_reviews": len(reviews)
    })

    return {
        "avg_rating": avg_rating,
        "sentiment": sentiment_avg,
        "total_reviews": len(reviews),
        "texts": texts[:100],
        "monthly": monthly_data,
        "ratings": ratings,
        "sentiments": sentiments,
        "top_issues": top_issues,
        "top_strengths": top_strengths,
        "review_velocity": review_velocity,
        "rating_distribution": rating_distribution,
        "ai_growth_score": ai_growth_score
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
        "Happy" if s > 0.5 else
        "Angry" if s < -0.3 else
        "Neutral"
        for s in data["sentiments"]
    ]

    return JSONResponse(content={
        "kpis": {
            "rating": data["avg_rating"],
            "reviews": data["total_reviews"],
            "sentiment": data["sentiment"],
            "risk": risk,
            "top_issues": data["top_issues"],
            "top_strengths": data["top_strengths"],
            "ai_growth_score": data["ai_growth_score"]
        },
        "charts": {
            "monthly_sentiment": data["monthly"],
            "review_velocity": data["review_velocity"],
            "emotions": dict(Counter(emotions)),
            "rating_distribution": data["rating_distribution"]
        },
        "last_100_reviews": data["texts"]
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
    common = Counter([w for w in words if len(w) > 4]).most_common(10)

    issues = [w for w, _ in common[:5]]
    strengths = [w for w, _ in common[5:10]]

    answer = ""
    if intent == "rating":
        answer = f"Your average rating is {data['avg_rating']} out of 5. Top issues: {', '.join(issues)}"
    elif intent == "issues":
        answer = f"The main issues based on recent reviews are: {', '.join(issues)}"
    elif intent == "strengths":
        answer = f"Strengths identified from customer feedback: {', '.join(strengths)}"
    elif intent == "improve":
        answer = f"Focus on improving: {', '.join(issues)} and enhancing the customer experience."
    else:
        answer = (
            f"Company Rating: {data['avg_rating']}, Sentiment: {data['sentiment']}, "
            f"Total Reviews: {data['total_reviews']}, AI Growth Score: {data['ai_growth_score']}. "
            f"Top Issues: {', '.join(issues)}. Strengths: {', '.join(strengths)}"
        )

    return {"answer": answer, "last_100_reviews": data["texts"]}

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
                "reviews": data["total_reviews"],
                "sentiment": data["sentiment"],
                "ai_growth_score": data["ai_growth_score"]
            })

    results_sorted = sorted(results, key=lambda x: x["ai_growth_score"], reverse=True)
    for idx, r in enumerate(results_sorted):
        r["rank"] = idx + 1
        r["percentile"] = round(100 * (len(results_sorted) - idx - 1) / max(len(results_sorted)-1, 1), 2)

    return {"comparison": results_sorted}

# ---------------- REVENUE ----------------

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
    impact = "HIGH" if risk > 50 else "MEDIUM" if risk > 25 else "LOW"
    projected_revenue_change = round((data["avg_rating"] - 3.5) * 2.5, 2)

    return {
        "risk_percent": round(risk, 2),
        "impact": impact,
        "projected_revenue_change": projected_revenue_change,
        "ai_growth_score": data["ai_growth_score"]
    }

# ---------------- AUTO REPLY ----------------

@router.post("/reply")
async def reply(review_text: str = Body(...)):
    score = analyzer.polarity_scores(review_text)["compound"]
    if score > 0:
        return {"reply": "Thank you for your positive feedback!"}
    else:
        return {"reply": "We apologize and will improve your experience."}
