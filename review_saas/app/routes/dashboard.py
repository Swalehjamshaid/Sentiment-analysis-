from __future__ import annotations
import os
import io
import logging
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.encoders import jsonable_encoder
from sqlalchemy import and_, select, func
from sqlalchemy.ext.asyncio import AsyncSession

# AI / ML / NLP Libraries
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from sklearn.feature_extraction.text import TfidfVectorizer

# Initialize AI Clients
try:
    from openai import OpenAI
    openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
except Exception:
    openai_client = None
    logging.warning("OpenAI client not initialized. Falling back to rule-based summaries.")

from app.core.db import get_session
from app.core.models import Company, Review

router = APIRouter(prefix="/api/ai", tags=["ai-insights"])

# ---------------- CONFIG ----------------
POS_THRESHOLD = 0.05
NEG_THRESHOLD = -0.05
MAX_REVIEWS_LIMIT = 5000      # HIGH CAPACITY: Increased to 5000 to cross the 250 wall
AI_PROCESSING_LIMIT = 500     # Increased subset for deep text analysis
LAST_N_REVIEWS_DISPLAY = 100  
logger = logging.getLogger(__name__)
analyzer = SentimentIntensityAnalyzer()

# ---------------- HELPERS ----------------
def safe_parse_date(value: Optional[str], default: datetime) -> datetime:
    try:
        if not value: return default
        dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return default

def detect_emotion(score: float) -> str:
    if score > 0.6: return "Happy"
    elif score > 0.2: return "Satisfied"
    elif score < -0.5: return "Angry"
    elif score < -0.2: return "Frustrated"
    return "Neutral"

def generate_comprehensive_ai_summary(data: Dict[str, Any]) -> str:
    """
    Generates a 20-sentence professional summary providing deep business insights.
    """
    if not openai_client:
        return (f"AI Insight for {data['name']}: Your current CSAT is {data['csat']}%. "
                "The business is performing well but needs focus on staff responsiveness. "
                "Ensure that the 1-star ratings are addressed within 24 hours to improve reputation.")
    
    prompt = f"""
    You are a Lead Business Intelligence Strategy Consultant. 
    Analyze the following data for the business '{data['name']}':
    - Average Star Rating: {data['avg_rating']}/5
    - Customer Satisfaction (CSAT): {data['csat']}%
    - Total Review Volume: {data['count']}
    - Emotional Tone: {data['emotions']}
    - Top Mentioned Keywords: {', '.join(data['topics'])}

    TASK: Write a exactly 20-sentence COMPREHENSIVE STRATEGIC REPORT.
    The report must:
    1. Detail the current market reputation health based on the {data['avg_rating']} star average.
    2. Analyze the specific friction points suggested by the keywords {', '.join(data['topics'][:4])}.
    3. Evaluate the emotional landscape of your customers.
    4. Provide 5 distinct, high-impact operational steps the management must take immediately to increase the CSAT score.
    5. Use professional, data-driven, and authoritative business language suitable for a logistics or service manager.
    """
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a senior analyst. You always provide deep, 20-sentence strategic insights."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=1000,
            temperature=0.7
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"OpenAI API Error: {e}")
        return "Manual Analysis Required: Quota exceeded or API down. Based on ratings, prioritize service speed."

# ---------------- MAIN ROUTE ----------------
@router.get("/insights")
async def get_dashboard_insights(
    company_id: int = Query(...),
    start: Optional[str] = None,
    end: Optional[str] = None,
    session: AsyncSession = Depends(get_session)
):
    company = await session.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    start_d = safe_parse_date(start, datetime.now(timezone.utc) - timedelta(days=730))
    end_d = safe_parse_date(end, datetime.now(timezone.utc))

    stmt = (
        select(Review)
        .where(and_(
            Review.company_id == company_id,
            Review.google_review_time >= start_d,
            Review.google_review_time <= end_d
        ))
        .order_by(Review.google_review_time.desc())
        .limit(MAX_REVIEWS_LIMIT)
    )
    res = await session.execute(stmt)
    reviews = res.scalars().all()
    
    if not reviews:
        return {"status": "success", "ai_insights": {"summary": "No data found."}}

    # Aggregators
    sentiments, texts, emotions, ratings = [], [], [], []
    monthly_trend = defaultdict(lambda: {"count": 0, "sentiment": 0.0})
    last_100_reviews = []

    for r in reviews:
        text = (r.text or "").strip()
        score = r.sentiment_score if r.sentiment_score is not None else analyzer.polarity_scores(text)["compound"]
        
        sentiments.append(score)
        texts.append(text)
        emotions.append(detect_emotion(score))
        ratings.append(r.rating)

        if len(last_100_reviews) < LAST_N_REVIEWS_DISPLAY:
            last_100_reviews.append({
                "date": r.google_review_time.strftime("%Y-%m-%d"),
                "author": r.author_name,
                "rating": r.rating,
                "text": text[:150] + "...",
                "sentiment_label": "Positive" if score > POS_THRESHOLD else ("Negative" if score < NEG_THRESHOLD else "Neutral")
            })

        if r.google_review_time:
            month_key = r.google_review_time.strftime("%Y-%m")
            monthly_trend[month_key]["count"] += 1
            monthly_trend[month_key]["sentiment"] += score

    total = len(sentiments)
    avg_sentiment = sum(sentiments)/total
    avg_rating = sum(ratings)/total
    csat_val = round((len([s for s in sentiments if s > POS_THRESHOLD])/total)*100, 1)

    # 5. Topic extraction
    ai_subset = texts[:AI_PROCESSING_LIMIT]
    topics = []
    if len(ai_subset) > 5:
        try:
            vectorizer = TfidfVectorizer(stop_words="english", max_features=10)
            vectorizer.fit_transform(ai_subset)
            topics = vectorizer.get_feature_names_out().tolist()
        except:
            topics = ["service", "staff", "quality"]

    # 6. Generate 20-Sentence Strategic Summary
    ai_summary = generate_comprehensive_ai_summary({
        "name": company.name,
        "avg_rating": round(avg_rating, 2),
        "avg_sentiment": round(avg_sentiment, 2),
        "csat": csat_val,
        "count": total,
        "topics": topics,
        "emotions": dict(Counter(emotions))
    })

    return JSONResponse(content=jsonable_encoder({
        "metadata": {"company": company.name, "processed_count": total},
        "kpis": {
            "reputation_score": round((avg_sentiment + 1) * 50, 1),
            "csat": csat_val,
            "benchmark": {"your_avg": round(avg_rating, 2), "category_avg": 4.1}
        },
        "visualizations": {
            "monthly_analytics": [{"month": m, "avg_sentiment": round(d["sentiment"]/d["count"], 2), "volume": d["count"]} 
                                  for m, d in sorted(monthly_trend.items())],
            "emotions": dict(Counter(emotions)),
            "rating_distribution": dict(Counter(ratings)) # NEW: For Star Rating Chart
        },
        "ai_insights": {
            "summary": ai_summary,
            "topics": topics
        },
        "recent_reviews": last_100_reviews
    }))
