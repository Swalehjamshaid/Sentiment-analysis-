from __future__ import annotations
import os
import logging
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.encoders import jsonable_encoder
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from sklearn.feature_extraction.text import TfidfVectorizer

from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

try:
    from openai import OpenAI
    openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
except:
    openai_client = None

from app.core.db import get_session
from app.core.models import Company, Review

router = APIRouter(prefix="/api/ai", tags=["AI Dashboard"])
logger = logging.getLogger(__name__)
analyzer = SentimentIntensityAnalyzer()

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


def generate_pdf(summary):
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


# ---------------- CORE ANALYSIS FUNCTION ----------------

async def analyze_company(session, company_id, start_d, end_d):
    stmt = select(Review).where(
        and_(
            Review.company_id == company_id,
            Review.google_review_time >= start_d,
            Review.google_review_time <= end_d
        )
    )

    res = await session.execute(stmt)
    reviews = res.scalars().all()

    if not reviews:
        return None

    sentiments, ratings, texts = [], [], []

    for r in reviews:
        text = (r.text or "")
        score = analyzer.polarity_scores(text)["compound"]

        sentiments.append(score)
        ratings.append(r.rating)
        texts.append(text)

    avg_rating = sum(ratings) / len(ratings)
    sentiment_avg = sum(sentiments) / len(sentiments)

    return {
        "avg_rating": round(avg_rating, 2),
        "sentiment": round(sentiment_avg, 2),
        "total_reviews": len(reviews),
        "texts": texts[:200]
    }


# ---------------- MAIN DASHBOARD ----------------

@router.get("/insights")
async def dashboard(
    company_id: int,
    start: Optional[str] = None,
    end: Optional[str] = None,
    pdf: Optional[bool] = False,
    session: AsyncSession = Depends(get_session)
):
    start_d = safe_date(start, datetime.now(timezone.utc) - timedelta(days=365))
    end_d = safe_date(end, datetime.now(timezone.utc))

    data = await analyze_company(session, company_id, start_d, end_d)
    if not data:
        return {"status": "no_data"}

    risk_score = max(0, (1 - data["sentiment"]) * 50)

    summary = f"""
    Business Rating: {data['avg_rating']}
    Total Reviews: {data['total_reviews']}
    Risk Score: {risk_score}
    """

    if pdf:
        return StreamingResponse(generate_pdf(summary), media_type="application/pdf")

    return JSONResponse(content={
        "kpis": data,
        "risk_score": risk_score,
        "summary": summary
    })


# ---------------- 🤖 AI CHATBOT ----------------

@router.post("/chat")
async def ai_chat(
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
        raise HTTPException(404, "No data")

    context = f"""
    Rating: {data['avg_rating']}
    Reviews: {data['total_reviews']}
    Sentiment: {data['sentiment']}
    """

    if openai_client:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a business consultant"},
                {"role": "user", "content": context + "\n" + question}
            ]
        )
        answer = response.choices[0].message.content
    else:
        answer = "AI not configured"

    return {"answer": answer}


# ---------------- 🥊 COMPETITOR COMPARISON ----------------

@router.post("/compare")
async def compare_companies(
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
            results.append({"company_id": cid, **data})

    best = max(results, key=lambda x: x["avg_rating"]) if results else None

    return {
        "comparison": results,
        "leader": best
    }


# ---------------- 💰 REVENUE PREDICTION ----------------

@router.get("/revenue-risk")
async def revenue_prediction(
    company_id: int,
    session: AsyncSession = Depends(get_session)
):
    data = await analyze_company(
        session,
        company_id,
        datetime.now(timezone.utc) - timedelta(days=365),
        datetime.now(timezone.utc)
    )

    if not data:
        return {"status": "no_data"}

    risk = (1 - data["sentiment"]) * 100

    impact = "LOW"
    if risk > 60:
        impact = "HIGH"
    elif risk > 30:
        impact = "MEDIUM"

    return {
        "risk_percentage": round(risk, 2),
        "impact_level": impact,
        "estimated_revenue_loss": f"{round(risk * 1000)} USD"
    }


# ---------------- ✍️ AUTO REPLY ----------------

@router.post("/auto-reply")
async def auto_reply(
    review_text: str = Body(...),
):
    score = analyzer.polarity_scores(review_text)["compound"]

    if openai_client:
        prompt = f"Generate a professional reply to this review:\n{review_text}"
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}]
        )
        reply = response.choices[0].message.content
    else:
        if score > 0:
            reply = "Thank you for your positive feedback!"
        else:
            reply = "We apologize and will improve."

    return {
        "sentiment": sentiment_label(score),
        "reply": reply
    }
