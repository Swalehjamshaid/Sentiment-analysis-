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
MAX_REVIEWS_LIMIT = 1000      # Increased for high-capacity analysis
AI_PROCESSING_LIMIT = 100     # Limit for Keyword Extraction
LAST_N_REVIEWS_DISPLAY = 100  # Number of reviews for the UI table
logger = logging.getLogger(__name__)
analyzer = SentimentIntensityAnalyzer()

# ---------------- HELPERS ----------------
def safe_parse_date(value: Optional[str], default: datetime) -> datetime:
    try:
        if not value: return default
        # Handle 'Z' suffix from frontend ISO strings
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

def generate_executive_summary(data: Dict[str, Any]) -> str:
    """
    Generates a professional, comprehensive summary using GPT-4o-mini.
    """
    if not openai_client:
        return (f"EXECUTIVE SUMMARY for {data['name']}: Reputation is currently stable with an average "
                f"rating of {data['avg_rating']}/5. Customer sentiment is focused on keywords like "
                f"{', '.join(data['topics'][:3])}. ACTIONABLE: Focus on maintaining high response "
                "rates to neutral feedback to drive higher CSAT scores.")
    
    prompt = f"""
    You are a Senior Business Intelligence Consultant. Analyze these metrics for {data['name']}:
    - Average Rating: {data['avg_rating']}/5
    - Net Sentiment: {data['avg_sentiment']} (Range -1 to 1)
    - Review Volume: {data['count']}
    - Top Mentioned Keywords: {', '.join(data['topics'])}

    Provide a COMPREHENSIVE executive report including:
    1. Overall Reputation Health & Market Sentiment.
    2. Deep Dive into Customer Friction & Satisfaction Trends.
    3. Three specific, high-impact actionable strategies to improve business operations.
    Use professional, objective, and executive-level language.
    """
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are an expert business analyst providing executive-level insights."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=600,
            temperature=0.7
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"OpenAI API Error: {e}")
        return "Manual Analysis Recommended: Current data indicates high volume but requires direct review for staff-related trends."

# ---------------- MAIN ROUTE ----------------
@router.get("/insights")
async def get_dashboard_insights(
    company_id: int = Query(...),
    start: Optional[str] = None,
    end: Optional[str] = None,
    session: AsyncSession = Depends(get_session)
):
    # 1. Fetch Company Metadata
    company = await session.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    # 2. Date Parsing (Aligned with UI filters)
    start_d = safe_parse_date(start, datetime.now(timezone.utc) - timedelta(days=730))
    end_d = safe_parse_date(end, datetime.now(timezone.utc))

    # 3. DB Query
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
        return {
            "status": "success", 
            "metadata": {"company": company.name}, 
            "kpis": {"reputation_score": 0}, 
            "ai_insights": {"summary": "No data found for the selected period."}
        }

    # 4. Analytics Data Aggregation
    sentiments, texts, emotions = [], [], []
    weekly_trend = defaultdict(lambda: {"count": 0, "sentiment": 0.0})
    monthly_trend = defaultdict(lambda: {"count": 0, "sentiment": 0.0, "rating_sum": 0.0})
    last_100_reviews = []

    for r in reviews:
        text = (r.text or "").strip()
        # Use existing score from DB or calculate if missing
        score = r.sentiment_score if r.sentiment_score is not None else analyzer.polarity_scores(text)["compound"]
        
        sentiments.append(score)
        texts.append(text)
        emotions.append(detect_emotion(score))

        # Table Data Mapping (100 Records)
        if len(last_100_reviews) < LAST_N_REVIEWS_DISPLAY:
            last_100_reviews.append({
                "date": r.google_review_time.strftime("%Y-%m-%d"),
                "author": r.author_name,
                "rating": r.rating,
                "text": text[:200] + "..." if len(text) > 200 else text,
                "sentiment_label": "Positive" if score > POS_THRESHOLD else ("Negative" if score < NEG_THRESHOLD else "Neutral")
            })

        # Process Trends (Month and Week)
        if r.google_review_time:
            week_key = r.google_review_time.strftime("%Y-W%U")
            month_key = r.google_review_time.strftime("%Y-%m")
            
            # Weekly stats
            weekly_trend[week_key]["count"] += 1
            weekly_trend[week_key]["sentiment"] += score
            
            # Monthly stats (Month-Wise Analytics)
            monthly_trend[month_key]["count"] += 1
            monthly_trend[month_key]["sentiment"] += score
            monthly_trend[month_key]["rating_sum"] += r.rating

    total = len(sentiments)
    avg_sentiment = sum(sentiments)/total
    avg_rating = sum(r.rating for r in reviews)/total

    # 5. Topic extraction from recent subset
    ai_subset = texts[:AI_PROCESSING_LIMIT]
    topics = []
    if len(ai_subset) > 5:
        try:
            vectorizer = TfidfVectorizer(stop_words="english", max_features=8)
            vectorizer.fit_transform(ai_subset)
            topics = vectorizer.get_feature_names_out().tolist()
        except Exception:
            topics = ["service", "quality", "experience"]

    # 6. Comprehensive AI Summary Generation
    ai_summary = generate_executive_summary({
        "name": company.name,
        "avg_rating": round(avg_rating, 2),
        "avg_sentiment": round(avg_sentiment, 2),
        "count": total,
        "topics": topics
    })

    # 7. Construct Response
    response = {
        "metadata": {
            "company": company.name, 
            "processed_count": total,
            "period": f"{start_d.date()} to {end_d.date()}"
        },
        "kpis": {
            "reputation_score": round((avg_sentiment + 1) * 50, 1),
            "csat": round((len([s for s in sentiments if s > POS_THRESHOLD])/total)*100, 1) if total > 0 else 0,
            "benchmark": {"your_avg": round(avg_rating, 2), "category_avg": 4.1}
        },
        "visualizations": {
            "sentiment_trend": [{"week": w, "avg": round(d["sentiment"]/d["count"], 2)} 
                                for w, d in sorted(weekly_trend.items())],
            "monthly_analytics": [{"month": m, "avg_sentiment": round(d["sentiment"]/d["count"], 2), "volume": d["count"]} 
                                  for m, d in sorted(monthly_trend.items())],
            "emotions": dict(Counter(emotions))
        },
        "ai_insights": {
            "summary": ai_summary,
            "topics": topics
        },
        "recent_reviews": last_100_reviews
    }

    return JSONResponse(content=jsonable_encoder(response))
