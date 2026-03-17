from __future__ import annotations
import os
import logging
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.encoders import jsonable_encoder
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from sklearn.feature_extraction.text import TfidfVectorizer

from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

# OpenAI
try:
    from openai import OpenAI
    openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
except:
    openai_client = None

from app.core.db import get_session
from app.core.models import Company, Review

router = APIRouter(prefix="/api/ai", tags=["ai-dashboard"])

logger = logging.getLogger(__name__)
analyzer = SentimentIntensityAnalyzer()

POS_THRESHOLD = 0.05
NEG_THRESHOLD = -0.05
MAX_LIMIT = 1000000
AI_LIMIT = 1000


# ---------------- HELPERS ----------------

def safe_date(val, default):
    try:
        if not val:
            return default
        d = datetime.fromisoformat(val.replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except:
        return default


def detect_spam(text: str) -> bool:
    if not text:
        return False
    spam_keywords = ["buy now", "click here", "visit", "offer", "free", "http"]
    return any(k in text.lower() for k in spam_keywords)


def sentiment_label(score: float) -> str:
    if score > POS_THRESHOLD:
        return "Positive"
    elif score < NEG_THRESHOLD:
        return "Negative"
    return "Neutral"


def python_ai_summary(data):
    return f"""
Business {data['name']} shows an average rating of {data['avg']} stars.
A total of {data['count']} reviews were analyzed.
Customer satisfaction stands at {data['csat']}%.
Top discussion topics include {', '.join(data['topics'][:5])}.
The dominant emotion is {data['emotion']}.
Operational improvements should focus on service consistency.
Introduce response systems for negative reviews.
Enhance customer experience in peak hours.
Strengthen staff training programs.
Implement weekly review audits.
    """


def generate_pdf(summary: str):
    from io import BytesIO
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer)
    styles = getSampleStyleSheet()

    story = []
    for line in summary.split("\n"):
        story.append(Paragraph(line, styles["Normal"]))
        story.append(Spacer(1, 10))

    doc.build(story)
    buffer.seek(0)
    return buffer


# ---------------- MAIN API ----------------

@router.get("/insights")
async def dashboard(
    company_id: int = Query(...),
    start: Optional[str] = None,
    end: Optional[str] = None,
    pdf: Optional[bool] = False,
    session: AsyncSession = Depends(get_session)
):
    company = await session.get(Company, company_id)
    if not company:
        raise HTTPException(404, "Company not found")

    start_d = safe_date(start, datetime.now(timezone.utc) - timedelta(days=3650))
    end_d = safe_date(end, datetime.now(timezone.utc))

    stmt = select(Review).where(
        and_(
            Review.company_id == company_id,
            Review.google_review_time >= start_d,
            Review.google_review_time <= end_d
        )
    ).order_by(Review.google_review_time.desc()).limit(MAX_LIMIT)

    res = await session.execute(stmt)
    reviews = res.scalars().all()

    if not reviews:
        return {"status": "no_data"}

    sentiments, ratings, texts, emotions = [], [], [], []
    monthly = defaultdict(lambda: {"count": 0, "sum": 0})

    recent_reviews = []

    for r in reviews:
        text = (r.text or "").strip()
        score = r.sentiment_score or analyzer.polarity_scores(text)["compound"]

        sentiments.append(score)
        ratings.append(r.rating)
        texts.append(text)

        label = sentiment_label(score)

        # Emotion
        if score > 0.6:
            emotions.append("Happy")
        elif score > 0.2:
            emotions.append("Satisfied")
        elif score < -0.5:
            emotions.append("Angry")
        elif score < -0.2:
            emotions.append("Frustrated")
        else:
            emotions.append("Neutral")

        # Monthly
        if r.google_review_time:
            key = r.google_review_time.strftime("%Y-%m")
            monthly[key]["count"] += 1
            monthly[key]["sum"] += score

        # Latest 100 Reviews (Frontend requirement)
        if len(recent_reviews) < 100:
            recent_reviews.append({
                "date": r.google_review_time.strftime("%Y-%m-%d") if r.google_review_time else "",
                "author": r.author_name or "Anonymous",
                "rating": r.rating,
                "text": text,
                "sentiment_label": label,
                "is_spam": detect_spam(text)
            })

    total = len(sentiments)
    avg = round(sum(ratings)/total, 2)
    csat = round((len([s for s in sentiments if s > POS_THRESHOLD])/total)*100, 1)

    topics = []
    if len(texts) > 5:
        try:
            vec = TfidfVectorizer(stop_words='english', max_features=10)
            vec.fit(texts[:AI_LIMIT])
            topics = vec.get_feature_names_out().tolist()
        except:
            topics = ["service", "quality"]

    top_emotion = Counter(emotions).most_common(1)[0][0]

    # AI Summary
    if openai_client:
        try:
            prompt = f"""
            Analyze business {company.name}.
            Rating: {avg}, Reviews: {total}, Topics: {topics}.
            Give executive insights + actions.
            """
            res_ai = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=700
            )
            summary = res_ai.choices[0].message.content
        except:
            summary = python_ai_summary({
                "name": company.name,
                "avg": avg,
                "count": total,
                "csat": csat,
                "topics": topics,
                "emotion": top_emotion
            })
    else:
        summary = python_ai_summary({
            "name": company.name,
            "avg": avg,
            "count": total,
            "csat": csat,
            "topics": topics,
            "emotion": top_emotion
        })

    # PDF Export
    if pdf:
        pdf_buffer = generate_pdf(summary)
        return StreamingResponse(pdf_buffer, media_type="application/pdf")

    monthly_data = [
        {
            "month": m,
            "avg_sentiment": round(v["sum"]/v["count"], 2)
        }
        for m, v in sorted(monthly.items())
    ]

    return JSONResponse(content=jsonable_encoder({
        "metadata": {
            "company": company.name,
            "processed_count": total
        },
        "kpis": {
            "reputation_score": round(((sum(sentiments)/total)+1)*50, 1),
            "csat": csat,
            "benchmark": {
                "your_avg": avg,
                "category_avg": 4.1
            }
        },
        "visualizations": {
            "monthly_analytics": monthly_data,
            "emotions": dict(Counter(emotions)),
            "rating_distribution": dict(Counter(ratings))
        },
        "ai_insights": {
            "summary": summary,
            "topics": topics
        },
        "recent_reviews": recent_reviews
    }))
