from __future__ import annotations
import os
import io
import logging
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.encoders import jsonable_encoder
from sqlalchemy import and_, select, func
from sqlalchemy.ext.asyncio import AsyncSession

# AI / ML Libraries
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import KMeans
import re

# Initialize Models globally to avoid reloading on every request
try:
    from sentence_transformers import SentenceTransformer
    embedder = SentenceTransformer("all-MiniLM-L6-v2")
except ImportError:
    embedder = None
    logging.warning("sentence-transformers not found. Semantic clustering disabled.")

try:
    from openai import OpenAI
    openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
except Exception:
    openai_client = None
    logging.warning("OpenAI client not initialized. GPT recommendations disabled.")

from reportlab.platypus import SimpleDocTemplate, Paragraph
from reportlab.lib.styles import getSampleStyleSheet

from app.core.db import get_session
from app.core.models import Company, Review

router = APIRouter(prefix="/api/ai", tags=["ai-insights"])

# ---------------- CONFIG ----------------
POS_THRESHOLD = 0.05
NEG_THRESHOLD = -0.05
MAX_REVIEWS_LIMIT = 50000
# SPEED FIX: Limit heavy transformer/clustering to most recent subset to hit < 60s target
AI_PROCESSING_LIMIT = 100 
FRAUD_SCORE_THRESHOLD = 0.9
LAST_N_REVIEWS = 50
logger = logging.getLogger(__name__)
analyzer = SentimentIntensityAnalyzer()

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

def detect_fraud(text: str) -> bool:
    spam_patterns = [r"free\s+gift", r"visit\s+this\s+link", r"buy\s+now", r"\$\d+"]
    return any(re.search(pat, text.lower()) for pat in spam_patterns)

def generate_ai_business_advice(data: Dict[str, Any]) -> str:
    if not openai_client:
        return "AI Offline: Check your OPENAI_API_KEY in Railway settings."
    
    prompt = f"""
    You are a Senior Business Intelligence Consultant. Analyze these metrics:
    - Average Rating: {data['avg_rating']}/5
    - Sentiment Score: {data['avg_sentiment']} (-1 to 1)
    - Staff Sentiment: {data['staff_positive']} positive, {data['staff_negative']} negative
    - Top Topics: {', '.join(data['topics'])}

    Provide a professional summary of reputation and 3 actionable recommendations.
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
        # FAILSAFE: If OpenAI 429 occurs, return a fallback instead of crashing the dashboard
        logger.error(f"OpenAI API Error: {e}")
        return "Maintain service standards and focus on resolving staff-related friction points identified in recent customer feedback."

def create_pdf_report(company_name: str, kpis: Dict[str, Any], insights: str) -> StreamingResponse:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer)
    styles = getSampleStyleSheet()
    content = [Paragraph(f"Company Dashboard Report: {company_name}", styles["Title"])]
    content.append(Paragraph(f"KPIs: {kpis}", styles["Normal"]))
    content.append(Paragraph(f"AI Insights: {insights}", styles["Normal"]))
    doc.build(content)
    buffer.seek(0)
    return StreamingResponse(buffer, media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename={company_name}_report.pdf"})

# ---------------- MAIN ROUTE ----------------
@router.get("/insights")
async def get_dashboard_insights(
    company_id: int = Query(...),
    start: Optional[str] = None,
    end: Optional[str] = None,
    pdf: bool = Query(False),
    session: AsyncSession = Depends(get_session)
):
    company = await session.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    start_d = safe_parse_date(start, datetime.now() - timedelta(days=730))
    end_d = safe_parse_date(end, datetime.now())

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
        return {"status": "success", "kpis": {"reputation_score": 0, "csat": 0},
                "visualizations": {}, "ai_insights": {"summary": "No data found."}}

    benchmark_stmt = select(func.avg(Review.rating)).join(Company).where(
        and_(Company.category == company.category, Company.id != company_id)
    )
    category_avg = (await session.execute(benchmark_stmt)).scalar() or 0.0

    weekly_trend = defaultdict(lambda: {"count": 0, "sentiment": 0.0})
    staff_mentions = {"positive": 0, "negative": 0}
    sentiments, texts, emotions = [], [], []
    fraud_reviews = []
    last_reviews = []

    for r in reviews:
        text = (r.text or "").strip()
        if not text: continue
        score = analyzer.polarity_scores(text)["compound"]
        sentiments.append(score)
        texts.append(text)
        emotions.append(detect_emotion(score))

        if any(word in text.lower() for word in ["staff", "service", "waiter", "manager"]):
            if score > POS_THRESHOLD: staff_mentions["positive"] += 1
            elif score < NEG_THRESHOLD: staff_mentions["negative"] += 1

        if detect_fraud(text):
            fraud_reviews.append({"text": text, "time": r.google_review_time})

        if r.google_review_time:
            week_key = r.google_review_time.strftime("%Y-W%U")
            weekly_trend[week_key]["count"] += 1
            weekly_trend[week_key]["sentiment"] += score

        if len(last_reviews) < LAST_N_REVIEWS:
            last_reviews.append({"text": text, "rating": r.rating, "time": r.google_review_time})

    total = len(sentiments)
    avg_sentiment = sum(sentiments)/total if total > 0 else 0
    avg_rating = sum(r.rating for r in reviews if r.rating)/total if total > 0 else 0

    # SPEED OPTIMIZATION: Use only latest 100 reviews for heavy NLP to keep processing < 60s
    ai_subset_texts = texts[:AI_PROCESSING_LIMIT]

    topics = []
    if len(ai_subset_texts) > 5:
        vectorizer = TfidfVectorizer(stop_words="english", max_features=10)
        vectorizer.fit_transform(ai_subset_texts)
        topics = vectorizer.get_feature_names_out().tolist()

    clusters = []
    if embedder and len(ai_subset_texts) > 5:
        embeddings = embedder.encode(ai_subset_texts)
        kmeans = KMeans(n_clusters=min(3, len(ai_subset_texts)), n_init=5)
        clusters = kmeans.fit_predict(embeddings).tolist()

    ai_recommendation = generate_ai_business_advice({
        "avg_rating": round(avg_rating, 2),
        "avg_sentiment": round(avg_sentiment, 2),
        "staff_positive": staff_mentions["positive"],
        "staff_negative": staff_mentions["negative"],
        "topics": topics
    })

    response = {
        "metadata": {"company": company.name, "processed_count": total},
        "kpis": {
            "reputation_score": round((avg_sentiment + 1) * 50, 1),
            "csat": round((len([s for s in sentiments if s > POS_THRESHOLD])/total)*100, 1) if total > 0 else 0,
            "benchmark": {"your_avg": round(avg_rating, 2), "category_avg": round(float(category_avg), 2)}
        },
        "visualizations": {
            "sentiment_trend": [{"week": w, "avg": round(d["sentiment"]/d["count"], 2)}
                                for w,d in sorted(weekly_trend.items())],
            "emotions": dict(Counter(emotions))
        },
        "ai_insights": {
            "summary": ai_recommendation,
            "topics": topics,
            "clusters": clusters
        },
        "fraud_alerts": fraud_reviews[:10],
        "last_reviews": last_reviews
    }

    if pdf:
        return create_pdf_report(company.name, response["kpis"], ai_recommendation)

    # SERIALIZATION FIX: jsonable_encoder converts Decimals/Dates for JSON safety
    return JSONResponse(content=jsonable_encoder(response))
