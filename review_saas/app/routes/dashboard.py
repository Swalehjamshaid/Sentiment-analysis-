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

# AI / ML
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import KMeans
from sentence_transformers import SentenceTransformer

# PDF
from reportlab.platypus import SimpleDocTemplate, Paragraph
from reportlab.lib.styles import getSampleStyleSheet

# OpenAI
try:
    from openai import OpenAI
    openai_client = OpenAI()
except Exception:
    openai_client = None

from app.core.db import get_session
from app.core.models import Company, Review

router = APIRouter(prefix="/api/ai", tags=["ai-insights"])

# ---------------- CONFIG ----------------
SPIKE_THRESHOLD = 10
POS_THRESHOLD = 0.05
NEG_THRESHOLD = -0.05
# REFINED: Increased to 50,000 to analyze the full historical data from Postgres
MAX_REVIEWS = 50000

analyzer = SentimentIntensityAnalyzer()
embedder = SentenceTransformer("all-MiniLM-L6-v2")

logger = logging.getLogger(__name__)

# ---------------- HELPERS ----------------

def safe_parse_date(value: Optional[str], default: datetime) -> datetime:
    try:
        return datetime.fromisoformat(value) if value else default
    except Exception:
        return default


def detect_emotion(score: float) -> str:
    if score > 0.6:
        return "Happy"
    elif score > 0.2:
        return "Satisfied"
    elif score < -0.5:
        return "Angry"
    elif score < -0.2:
        return "Frustrated"
    return "Neutral"


def detect_spam(text: str) -> bool:
    if len(text) < 10:
        return True
    if text.count("!") > 3:
        return True
    if text.lower().count("bad") > 5:
        return True
    return False


def generate_ai_summary(data: Dict[str, Any]) -> str:
    prompt = f"""
    You are a senior business analyst.

    Analyze:
    Rating: {data['avg_rating']}
    Sentiment: {data['avg_sentiment']}
    Negative Staff: {data['staff_negative']}
    Positive Staff: {data['staff_positive']}
    Topics: {', '.join(data['topics'])}

    Provide key insights and 3 recommendations.
    """

    if openai_client:
        try:
            response = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=200
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.warning(f"OpenAI error: {e}")

    return "Improve customer service and scale positive experiences."


def generate_pdf(summary: str):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer)
    styles = getSampleStyleSheet()
    story = [Paragraph(summary, styles["Normal"])]
    doc.build(story)
    buffer.seek(0)
    return buffer


# ---------------- MAIN ROUTE ----------------

@router.get("/insights")
async def get_dashboard_insights(
    company_id: int = Query(...),
    start: Optional[str] = None,
    end: Optional[str] = None,
    export_pdf: bool = False,
    session: AsyncSession = Depends(get_session)
):

    # Validate company
    company = await session.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    # REFINED: Lookback set to 730 days (2 years) to capture all ingested historical data
    start_d = safe_parse_date(start, datetime.now() - timedelta(days=730))
    end_d = safe_parse_date(end, datetime.now())

    # Fetch reviews
    stmt = (
        select(Review)
        .where(and_(
            Review.company_id == company_id,
            Review.google_review_time >= start_d,
            Review.google_review_time <= end_d
        ))
        .limit(MAX_REVIEWS)
    )

    res = await session.execute(stmt)
    reviews = res.scalars().all()

    if not reviews:
        return {"status": "success", "data": None}

    # Benchmark
    benchmark_stmt = select(func.avg(Review.rating)).join(Company).where(and_(
        Company.category == company.category,
        Company.id != company_id
    ))

    benchmark_res = await session.execute(benchmark_stmt)
    category_avg = benchmark_res.scalar() or 0.0

    # ---------------- PROCESSING ----------------
    heatmap = {d: {h: 0 for h in range(24)} for d in ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]}
    weekly_trend = defaultdict(lambda: {"count": 0, "sentiment": 0.0})
    author_counts = Counter()
    staff_mentions = {"positive": 0, "negative": 0}
    spam_flags = []
    sentiments = []
    texts = []
    emotions = []

    for r in reviews:
        text = (r.text or "").strip()
        if not text:
            continue

        score = analyzer.polarity_scores(text)["compound"]

        sentiments.append(score)
        texts.append(text)
        emotions.append(detect_emotion(score))
        spam_flags.append(detect_spam(text))

        if "staff" in text.lower():
            if score > POS_THRESHOLD:
                staff_mentions["positive"] += 1
            elif score < NEG_THRESHOLD:
                staff_mentions["negative"] += 1

        if r.google_review_time:
            dt = r.google_review_time
            heatmap[dt.strftime("%a")][dt.hour] += 1

            week_key = dt.strftime("%Y-W%U")
            weekly_trend[week_key]["count"] += 1
            weekly_trend[week_key]["sentiment"] += score

        author_counts[r.author_name] += 1

    # ---------------- AGGREGATIONS ----------------
    total = len(sentiments)
    avg_sentiment = sum(sentiments) / total
    avg_rating = sum(r.rating for r in reviews if r.rating) / total

    # ---------------- SEMANTIC CLUSTERING ----------------
    clusters = []
    if len(texts) > 5:
        embeddings = embedder.encode(texts)
        kmeans = KMeans(n_clusters=3, n_init=10)
        clusters = kmeans.fit_predict(embeddings).tolist()

    # ---------------- TOPICS ----------------
    topics = []
    if len(texts) > 5:
        vectorizer = TfidfVectorizer(stop_words="english", max_features=50)
        X = vectorizer.fit_transform(texts)
        terms = vectorizer.get_feature_names_out()
        topics = terms[:10].tolist()

    # ---------------- AI SUMMARY ----------------
    ai_summary = generate_ai_summary({
        "avg_rating": avg_rating,
        "avg_sentiment": avg_sentiment,
        "staff_positive": staff_mentions["positive"],
        "staff_negative": staff_mentions["negative"],
        "topics": topics
    })

    # ---------------- PDF EXPORT ----------------
    if export_pdf:
        pdf = generate_pdf(ai_summary)
        return StreamingResponse(pdf, media_type="application/pdf")

    # ---------------- RESPONSE ----------------
    return {
        "metadata": {
            "company": company.name,
            "total_reviews": total
        },
        "kpis": {
            "reputation_score": round((avg_sentiment + 1) * 50, 1),
            "csat": round((len([s for s in sentiments if s > POS_THRESHOLD]) / total) * 100, 1),
            "loyal_customers": len([c for c in author_counts.values() if c > 1]),
            "benchmark": {
                "your_avg": round(avg_rating, 2),
                "category_avg": round(category_avg, 2)
            }
        },
        "visualizations": {
            "heatmap": heatmap,
            "sentiment_trend": [
                {"week": w, "avg": round(d["sentiment"]/d["count"], 2)}
                for w, d in weekly_trend.items()
            ],
            "emotions": dict(Counter(emotions))
        },
        "ai_insights": {
            "summary": ai_summary,
            "topics": topics,
            "clusters": clusters,
            "spam_detected": sum(spam_flags)
        }
    }
