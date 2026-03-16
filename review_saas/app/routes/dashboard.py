# filename: app/routes/dashbord.py

from __future__ import annotations
import re
from collections import Counter, defaultdict
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, select, func
from sqlalchemy.ext.asyncio import AsyncSession

# AI & NLP Libraries
import spacy
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from sklearn.feature_extraction.text import TfidfVectorizer

from app.core.db import get_session
from app.core.models import Company, Review

router = APIRouter(prefix="/api/ai", tags=["ai-insights"])

# Global Initialization - Optimized for real-time performance
try:
    # Selective pipeline: disable components not needed for basic extraction
    nlp = spacy.load("en_core_web_sm", disable=["parser", "ner", "lemmatizer"])
except OSError:
    nlp = None

analyzer = SentimentIntensityAnalyzer()

# -------------------- BI & AI Logic Helpers --------------------

EMOTION_KEYWORDS = {
    "Happy": {"happy", "great", "love", "amazing", "excellent", "best", "wonderful"},
    "Angry": {"angry", "furious", "worst", "terrible", "awful", "hate"},
    "Frustrated": {"slow", "wait", "disappointed", "annoyed", "irritated", "back"},
    "Satisfied": {"good", "fine", "ok", "satisfied", "content", "standard"}
}

STAFF_KEYWORDS = {"staff", "waiter", "manager", "employee", "service", "team", "crew"}

def detect_emotion(text: str) -> str:
    """Requirement #2: Customer Emotion Detection"""
    text = text.lower()
    for emotion, keywords in EMOTION_KEYWORDS.items():
        if any(word in text for word in keywords):
            return emotion
    # Fallback to sentiment intensity
    score = analyzer.polarity_scores(text)['compound']
    return "Satisfied" if score > 0.5 else "Neutral"

# -------------------- Main Dashboard Analytics Engine --------------------

@router.get("/insights")
async def get_dashboard_insights(
    company_id: int = Query(...),
    start: Optional[str] = None,
    end: Optional[str] = None,
    session: AsyncSession = Depends(get_session)
):
    # 1. Fetch Company and Review Data
    company = await session.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    start_d = datetime.fromisoformat(start) if start else datetime.now() - timedelta(days=30)
    end_d = datetime.fromisoformat(end) if end else datetime.now()

    # Load reviews for the target company
    stmt = select(Review).where(and_(
        Review.company_id == company_id,
        Review.google_review_time >= start_d,
        Review.google_review_time <= end_d
    ))
    res = await session.execute(stmt)
    reviews = res.scalars().all()

    if not reviews:
        return {"status": "success", "data": None, "message": "No reviews found"}

    # 2. Category Benchmark Calculation (#9)
    benchmark_stmt = select(func.avg(Review.rating)).join(Company).where(and_(
        Company.category == company.category,
        Company.id != company_id,
        Review.google_review_time >= start_d,
        Review.google_review_time <= end_d
    ))
    benchmark_res = await session.execute(benchmark_stmt)
    category_avg = benchmark_res.scalar() or 0.0

    # 3. Real-time Processing Loop (Single-pass)
    all_text = []
    heatmap = {day: {hour: 0 for hour in range(24)} for day in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]}
    weekly_trend = defaultdict(lambda: {"count": 0, "sentiment": 0.0})
    author_counts = Counter()
    staff_mentions = {"positive": 0, "negative": 0}
    hourly_extreme_counts = defaultdict(int)

    for r in reviews:
        text = r.text or ""
        all_text.append(text)
        score = analyzer.polarity_scores(text)['compound']
        
        # Staff performance (#16)
        if any(kw in text.lower() for kw in STAFF_KEYWORDS):
            if score > 0.05: staff_mentions["positive"] += 1
            elif score < -0.05: staff_mentions["negative"] += 1
        
        # Heatmap (#18) & Trend (#14) logic
        if r.google_review_time:
            dt = r.google_review_time
            day_name = dt.strftime("%a")
            hour_val = dt.hour
            heatmap[day_name][hour_val] += 1
            
            # Anomaly Tracking: 1 or 5 star spikes (#11)
            if r.rating in [1, 5]:
                hour_bucket = dt.replace(minute=0, second=0, microsecond=0)
                hourly_extreme_counts[(hour_bucket, r.rating)] += 1
            
            # Weekly trend
            week_key = dt.strftime("%Y-W%U")
            weekly_trend[week_key]["count"] += 1
            weekly_trend[week_key]["sentiment"] += score

        author_counts[r.author_name] += 1

    # 4. Final Aggregations
    avg_rating = sum(r.rating for r in reviews if r.rating) / len(reviews)
    avg_sentiment = sum(analyzer.polarity_scores(t)['compound'] for t in all_text) / len(reviews)
    
    # Check for Rating Spikes (Threshold: 10)
    spike_incidents = [c for c in hourly_extreme_counts.values() if c > 10]
    
    # Topic Clustering (#5)
    topics = []
    if len(all_text) > 1:
        vectorizer = TfidfVectorizer(stop_words='english', max_features=10)
        vectorizer.fit_transform(all_text)
        topics = vectorizer.get_feature_names_out().tolist()

    # 5. Return Complete BI Payload
    return {
        "metadata": {
            "company_name": company.name,
            "total_reviews": len(reviews),
            "alert_status": len(spike_incidents) > 0
        },
        "kpi_metrics": {
            "reputation_score": round((avg_sentiment + 1) * 50, 1),
            "csat": round((len([t for t in all_text if analyzer.polarity_scores(t)['compound'] > 0.05]) / len(reviews)) * 100, 1),
            "loyalty_count": len([n for n, c in author_counts.items() if c > 1]),
            "benchmark": {
                "your_avg": round(avg_rating, 2),
                "category_avg": round(category_avg, 2)
            }
        },
        "visualizations": {
            "sentiment_trend": [
                {"week": w, "avg_sentiment": round(d["sentiment"]/d["count"], 2), "volume": d["count"]} 
                for w, d in sorted(weekly_trend.items())
            ],
            "activity_heatmap": heatmap,
            "emotion_radar": dict(Counter([detect_emotion(t) for t in all_text])),
            "staff_insights": staff_mentions
        },
        "ai_analysis": {
            "top_topics": topics,
            "suspicious_spikes_count": len(spike_incidents),
            "improvement_suggestion": "Focus on staff service quality" if staff_mentions["negative"] > staff_mentions["positive"] else "Expand successful products"
        }
    }
