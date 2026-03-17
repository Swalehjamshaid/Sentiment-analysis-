# filename: app/routes/dashboard.py

from __future__ import annotations

import os
import io
import logging
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import and_, select, func
from sqlalchemy.ext.asyncio import AsyncSession

# AI / ML - Using try-except to prevent the "Module Not Found" crash in Railway
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import KMeans

try:
    from sentence_transformers import SentenceTransformer
    # Initialize embedder globally for efficiency
    embedder = SentenceTransformer("all-MiniLM-L6-v2")
except ImportError:
    embedder = None
    logging.warning("sentence-transformers not found. Semantic clustering will be disabled.")

# PDF Generation Utilities
from reportlab.platypus import SimpleDocTemplate, Paragraph
from reportlab.lib.styles import getSampleStyleSheet

# OpenAI Integration for Recommendations
try:
    from openai import OpenAI
    # Requires OPENAI_API_KEY in Railway Environment Variables
    openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
except Exception:
    openai_client = None

from app.core.db import get_session
from app.core.models import Company, Review

router = APIRouter(prefix="/api/ai", tags=["ai-insights"])

# ---------------- CONFIG ----------------
POS_THRESHOLD = 0.05
NEG_THRESHOLD = -0.05
MAX_REVIEWS_LIMIT = 50000

analyzer = SentimentIntensityAnalyzer()
logger = logging.getLogger(__name__)

# ---------------- HELPERS ----------------

def safe_parse_date(value: Optional[str], default: datetime) -> datetime:
    try:
        return datetime.fromisoformat(value) if value else default
    except Exception:
        return default

def detect_emotion(score: float) -> str:
    if score > 0.6: return "Happy"
    elif score > 0.2: return "Satisfied"
    elif score < -0.5: return "Angry"
    elif score < -0.2: return "Frustrated"
    return "Neutral"

def generate_ai_business_advice(data: Dict[str, Any]) -> str:
    """Generates professional business recommendations using OpenAI GPT-4o-mini."""
    if not openai_client:
        return "AI Analysis Offline: Please verify your OPENAI_API_KEY in the Railway dashboard settings."

    prompt = f"""
    You are a Senior Business Intelligence Consultant. Analyze these review metrics:
    - Average Rating: {data['avg_rating']}/5
    - Sentiment Score: {data['avg_sentiment']} (-1 to 1)
    - Staff Sentiment: {data['staff_positive']} positive mentions, {data['staff_negative']} negative mentions.
    - Top Topics: {', '.join(data['topics'])}

    Provide a professional summary of the current reputation and 3 actionable business recommendations to improve customer loyalty.
    """

    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a helpful business analyst."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=300,
            temperature=0.7
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"OpenAI API Error: {e}")
        return "Maintain current service standards and focus on resolving staff-related friction points identified in recent feedback."

# ---------------- MAIN ROUTE ----------------

@router.get("/insights")
async def get_dashboard_insights(
    company_id: int = Query(...),
    start: Optional[str] = None,
    end: Optional[str] = None,
    session: AsyncSession = Depends(get_session)
):
    # 1. Validate the Company
    company = await session.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    # 2. Setup Date Filters
    start_d = safe_parse_date(start, datetime.now() - timedelta(days=730))
    end_d = safe_parse_date(end, datetime.now())

    # 3. Database Query
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
        return {"status": "success", "kpis": {"reputation_score": 0, "csat": 0}, "visualizations": {}, "ai_insights": {"summary": "No data found for selected range."}}

    # 4. Category Benchmarking
    benchmark_stmt = select(func.avg(Review.rating)).join(Company).where(and_(
        Company.category == company.category,
        Company.id != company_id
    ))
    benchmark_res = await session.execute(benchmark_stmt)
    category_avg = benchmark_res.scalar() or 0.0

    # 5. Review Processing
    weekly_trend = defaultdict(lambda: {"count": 0, "sentiment": 0.0})
    staff_mentions = {"positive": 0, "negative": 0}
    sentiments, texts, emotions = [], [], []

    for r in reviews:
        text = (r.text or "").strip()
        if not text: continue

        score = analyzer.polarity_scores(text)["compound"]
        sentiments.append(score)
        texts.append(text)
        emotions.append(detect_emotion(score))

        # Advanced Staff Sentiment Logic
        if any(word in text.lower() for word in ["staff", "service", "waiter", "manager", "team"]):
            if score > POS_THRESHOLD: staff_mentions["positive"] += 1
            elif score < NEG_THRESHOLD: staff_mentions["negative"] += 1

        if r.google_review_time:
            week_key = r.google_review_time.strftime("%Y-W%U")
            weekly_trend[week_key]["count"] += 1
            weekly_trend[week_key]["sentiment"] += score

    total = len(sentiments)
    avg_sentiment = sum(sentiments) / total
    avg_rating = sum(r.rating for r in reviews if r.rating) / total

    # 6. Keyword Extraction (TF-IDF)
    topics = []
    if len(texts) > 5:
        vectorizer = TfidfVectorizer(stop_words="english", max_features=10)
        vectorizer.fit_transform(texts)
        topics = vectorizer.get_feature_names_out().tolist()

    # 7. Semantic Clustering (Safety Protected)
    clusters = []
    if embedder and len(texts) > 5:
        embeddings = embedder.encode(texts)
        kmeans = KMeans(n_clusters=3, n_init=10)
        clusters = kmeans.fit_predict(embeddings).tolist()

    # 8. Generate OpenAI Recommendation
    ai_recommendation = generate_ai_business_advice({
        "avg_rating": round(avg_rating, 2),
        "avg_sentiment": round(avg_sentiment, 2),
        "staff_positive": staff_mentions["positive"],
        "staff_negative": staff_mentions["negative"],
        "topics": topics
    })

    # 9. JSON Response Construction
    return {
        "metadata": {
            "company": company.name,
            "processed_count": total
        },
        "kpis": {
            "reputation_score": round((avg_sentiment + 1) * 50, 1),
            "csat": round((len([s for s in sentiments if s > POS_THRESHOLD]) / total) * 100, 1),
            "benchmark": {
                "your_avg": round(avg_rating, 2),
                "category_avg": round(category_avg, 2)
            }
        },
        "visualizations": {
            "sentiment_trend": [
                {"week": w, "avg": round(d["sentiment"]/d["count"], 2)}
                for w, d in sorted(weekly_trend.items())
            ],
            "emotions": dict(Counter(emotions))
        },
        "ai_insights": {
            "summary": ai_recommendation,
            "topics": topics,
            "clusters": clusters
        }
    }
