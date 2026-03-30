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

# ---------------- HELPERS ----------------
def safe_date(val: Optional[str], default: datetime) -> datetime:
    try:
        if not val: return default
        d = datetime.fromisoformat(val.replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return default

# ---------------- CORE ANALYSIS ----------------
async def analyze_company(
    session: AsyncSession, company_id: int, start_d: datetime, end_d: datetime
) -> Optional[Dict[str, Any]]:
    """
    Main Analytics Engine. 
    Strictly preserves all Review attributes for AI and Visualization.
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
        .order_by(Review.first_seen_at.asc())
    )

    res = await session.execute(stmt)
    reviews = res.scalars().all()

    if not reviews: return None

    sentiments: List[float] = []
    ratings: List[int] = []
    texts: List[str] = []
    trend_map = defaultdict(list)
    emotions_list = []

    for r in reviews:
        # 1. Sentiment Processing
        text_content = (r.text or "")
        score = analyzer.polarity_scores(text_content)["compound"]
        
        sentiments.append(score)
        ratings.append(r.rating if r.rating is not None else 0)
        texts.append(text_content)

        # 2. Emotion Mapping (Radar Chart)
        if score > 0.5: emotions_list.append("Joy")
        elif score > 0.1: emotions_list.append("Trust")
        elif score < -0.5: emotions_list.append("Anger")
        elif score < -0.1: emotions_list.append("Disgust")
        else: emotions_list.append("Neutral")

        # 3. Time Series Mapping (Trend Chart)
        # Using week format because frontend uses d.week
        plot_date = r.google_review_time or r.first_seen_at
        if plot_date:
            week_key = plot_date.strftime("%Y-W%U")
            trend_map[week_key].append(score)

    total_count = len(reviews)
    avg_rating = round(sum(ratings) / total_count, 2) if total_count else 0.0
    sentiment_avg = round(sum(sentiments) / total_count, 2) if total_count else 0.0

    # Format sentiment_trend for Chart.js
    sentiment_trend = [
        {"week": w, "avg": round(sum(v) / len(v), 2)}
        for w, v in sorted(trend_map.items())
    ]

    # Format ratings for Bar Chart (1★, 2★, etc.)
    counts = Counter(ratings)
    rating_dist = {f"{i}★": counts.get(i, 0) for i in range(1, 6)}

    return {
        "avg_rating": avg_rating,
        "sentiment": sentiment_avg,
        "total_reviews": total_count,
        "texts": texts,
        "visualizations": {
            "emotions": dict(Counter(emotions_list)),
            "sentiment_trend": sentiment_trend,
            "ratings": rating_dist
        }
    }

# ---------------- ROUTES ----------------

@router.get("/insights")
@router.get("/ai/insights") # Alias to match frontend JS triggerAllLoads()
async def dashboard_insights(
    company_id: int,
    start: Optional[str] = None,
    end: Optional[str] = None,
    session: AsyncSession = Depends(get_session),
):
    start_d = safe_date(start, datetime.now(timezone.utc) - timedelta(days=365))
    end_d = safe_date(end, datetime.now(timezone.utc))

    data = await analyze_company(session, company_id, start_d, end_d)
    
    if not data:
        return JSONResponse(content={"status": "no_data"}, status_code=200)

    # 100% Alignment with Frontend JSON Accessors
    return {
        "metadata": {
            "total_reviews": data["total_reviews"]
        },
        "kpis": {
            "benchmark": {
                "your_avg": data["avg_rating"]
            },
            "reputation_score": int((data["sentiment"] + 1) * 50)
        },
        "visualizations": data["visualizations"]
    }

@router.get("/revenue")
async def revenue_monitoring(company_id: int, session: AsyncSession = Depends(get_session)):
    """
    Returns specific attributes for the 'risk-card' in UI.
    """
    data = await analyze_company(
        session, company_id, 
        datetime.now(timezone.utc) - timedelta(days=365), 
        datetime.now(timezone.utc)
    )
    if not data: return {"risk_percent": 0, "impact": "N/A"}

    risk_val = (1 - data["sentiment"]) * 50
    return {
        "risk_percent": round(risk_val, 2),
        "impact": "CRITICAL" if risk_val > 40 else "HIGH" if risk_val > 20 else "LOW"
    }

@router.post("/chat")
async def chatbot_ai(
    company_id: int,
    question: str = Body(...), # Matches JS JSON.stringify(msg)
    session: AsyncSession = Depends(get_session),
):
    data = await analyze_company(
        session, company_id, 
        datetime.now(timezone.utc) - timedelta(days=365), 
        datetime.now(timezone.utc)
    )
    if not data: return {"answer": "No records found for analysis."}

    # Intent detection logic
    q = question.lower()
    if "rating" in q:
        ans = f"The business holds an average rating of {data['avg_rating']} stars."
    elif data['sentiment'] < 0:
        ans = "The current AI sentiment is leaning negative. I recommend addressing recent 1-star reviews."
    else:
        ans = f"Analysis of {data['total_reviews']} reviews shows healthy customer satisfaction."

    return {"answer": ans}
