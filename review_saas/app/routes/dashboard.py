# filename: app/routes/dashboard.py
# ==========================================================
# REVIEW INTELLIGENCE DASHBOARD — COMPLETE BACKEND
# ==========================================================
# FULLY INTEGRATED WITH FRONTEND
# Supports: KPIs, Emotion Radar, Sentiment Trend, 
# Rating Distribution, Latest 100 Reviews, AI Chat (DeepSeek),
# Revenue Risk, Executive PDF Report
# ==========================================================

from __future__ import annotations

import io
import os
import logging
import asyncio
import re
from datetime import datetime, timedelta
from collections import Counter, defaultdict
from typing import Dict, List, Any, Optional

from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func
from fpdf import FPDF
import httpx

from app.core.db import get_db
from app.core.models import Company, Review

# ----------------------------------------------------------
# Configuration
# ----------------------------------------------------------
router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])
logger = logging.getLogger("dashboard")

# DeepSeek API Configuration
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"

# Sentiment thresholds
NEGATIVE_RATINGS = {1, 2}
POSITIVE_RATINGS = {4, 5}
NEG_SENTIMENT_LIMIT = -0.2
POS_SENTIMENT_LIMIT = 0.2

# Stopwords for keyword extraction
STOPWORDS = {
    "the", "and", "with", "this", "that", "for", "from", "was", "were",
    "have", "has", "had", "very", "just", "they", "them", "their", "there",
    "but", "not", "are", "you", "your", "will", "can", "our", "all", "any",
    "get", "got", "said", "like", "would", "could", "also", "one", "two",
    "see", "look", "come", "went", "take", "make", "time", "day", "good",
    "bad", "great", "awesome", "amazing", "terrible", "horrible", "place",
    "service", "food", "customer", "experience", "really", "actually"
}

# Emotion keywords mapping
EMOTION_KEYWORDS = {
    "Joy": ["happy", "great", "amazing", "excellent", "fantastic", "wonderful", "love", "perfect", "awesome", "pleased", "satisfied", "delighted", "enjoy", "beautiful", "best", "nice", "cool"],
    "Anger": ["angry", "furious", "terrible", "awful", "horrible", "hate", "disgusting", "worst", "frustrated", "annoying", "useless", "waste", "mad", "upset", "irritated", "unacceptable", "poor"],
    "Sadness": ["sad", "disappointed", "unfortunate", "sorry", "regret", "depressing", "bad experience", "let down", "missed", "unhappy", "gloomy", "heartbreaking"],
    "Surprise": ["surprised", "unexpected", "shocked", "amazed", "astonished", "wow", "unbelievable", "remarkable", "stunning", "incredible"],
    "Fear": ["worried", "concerned", "scared", "afraid", "nervous", "anxious", "fear", "terrified", "risky", "dangerous", "unsafe"],
    "Love": ["love", "adore", "cherish", "appreciate", "grateful", "thankful", "blessed", "heartwarming", "wonderful", "affection", "admire", "respect"]
}

# ----------------------------------------------------------
# Helper Functions
# ----------------------------------------------------------
def safe_date(val: str | None) -> datetime | None:
    """Convert string to datetime safely"""
    if not val:
        return None
    try:
        return datetime.fromisoformat(val)
    except Exception:
        return None

def sanitize_pdf(text: str) -> str:
    """Sanitize text for PDF generation (FPDF compatibility)"""
    if not text:
        return ""
    replacements = {
        "—": "-", "–": "-", "’": "'", "“": '"', "”": '"',
        "•": "-", "…": "...", "©": "(C)", "®": "(R)", "é": "e",
        "è": "e", "ê": "e", "à": "a", "â": "a", "ô": "o", "ç": "c",
        "ñ": "n", "ü": "u", "ö": "o"
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
    return text.encode('latin-1', errors='ignore').decode('latin-1')

def extract_keywords(text: str) -> List[str]:
    """Extract meaningful keywords from review text"""
    if not text:
        return []
    words: List[str] = []
    cleaned = re.sub(r'[^\w\s]', ' ', text.lower())
    for w in cleaned.split():
        if len(w) >= 4 and w.isalpha() and w not in STOPWORDS:
            words.append(w)
    return words

def compute_emotion_scores(text: str) -> Dict[str, int]:
    """Calculate emotion scores based on keyword matching"""
    if not text:
        return {emotion: 0 for emotion in EMOTION_KEYWORDS}
    text_lower = text.lower()
    scores = {}
    for emotion, keywords in EMOTION_KEYWORDS.items():
        count = 0
        for kw in keywords:
            count += text_lower.count(kw)
        scores[emotion] = min(count * 5, 100)
    return scores

def get_sentiment_label(rating: Optional[int], sentiment_score: Optional[float]) -> str:
    """Determine sentiment label from rating or sentiment score"""
    if sentiment_score is not None:
        if sentiment_score <= NEG_SENTIMENT_LIMIT:
            return "negative"
        elif sentiment_score >= POS_SENTIMENT_LIMIT:
            return "positive"
        else:
            return "neutral"
    elif rating is not None:
        if rating <= 2:
            return "negative"
        elif rating >= 4:
            return "positive"
        else:
            return "neutral"
    return "neutral"

async def get_company(session: AsyncSession, company_id: int) -> Company:
    """Get company by ID or raise 404"""
    result = await session.execute(select(Company).where(Company.id == company_id))
    company = result.scalars().first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return company

async def call_deepseek_api(messages: List[Dict]) -> str:
    """Call DeepSeek API with the given messages"""
    if not DEEPSEEK_API_KEY:
        logger.warning("DEEPSEEK_API_KEY not set")
        return "⚠️ DeepSeek API key not configured."
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(
                DEEPSEEK_API_URL,
                headers={
                    "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "deepseek-chat",
                    "messages": messages,
                    "temperature": 0.7,
                    "max_tokens": 500
                }
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(f"DeepSeek API error: {e}")
            return "🔧 AI service is temporarily unavailable."

# ----------------------------------------------------------
# Core Analytics Engine
# ----------------------------------------------------------
def compute_complete_analytics(
    reviews: List[Review],
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None
) -> Dict[str, Any]:
    total_reviews = len(reviews)
    if total_reviews == 0:
        return {
            "metadata": {"total_reviews": 0, "recent_count": 0},
            "kpis": {"average_rating": 0.0, "reputation_score": 100.0},
            "visualizations": {
                "emotions": {e: 0 for e in EMOTION_KEYWORDS},
                "ratings": {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0},
                "sentiment_trend": []
            },
            "risk": {"loss_probability": "0%", "impact_level": "Low"}
        }

    ratings: List[int] = []
    rating_distribution = {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0}
    weekly_trend: Dict[str, List[float]] = defaultdict(list)
    emotion_accumulator: Dict[str, List[int]] = defaultdict(list)
    
    negative_count = 0
    severe_count = 0
    
    for review in reviews:
        if review.rating:
            rv = int(review.rating)
            rating_distribution[str(rv)] += 1
            ratings.append(rv)
            if rv in NEGATIVE_RATINGS: severe_count += 1
            
        if review.sentiment_score is not None:
            if review.sentiment_score <= NEG_SENTIMENT_LIMIT: negative_count += 1
        
        if review.text:
            emotions = compute_emotion_scores(review.text)
            for e, s in emotions.items(): emotion_accumulator[e].append(s)

        if review.google_review_time:
            week_key = (review.google_review_time - timedelta(days=review.google_review_time.weekday())).strftime("%Y-%m-%d")
            score = review.sentiment_score if review.sentiment_score is not None else (review.rating - 3) / 2
            weekly_trend[week_key].append(score)

    avg_rating = round(sum(ratings) / len(ratings), 2) if ratings else 0.0
    risk_pct = round(((negative_count * 0.6 + severe_count * 0.4) / total_reviews) * 100, 1)
    
    sentiment_trend = []
    for week_key in sorted(weekly_trend.keys())[-12:]:
        avg_s = sum(weekly_trend[week_key]) / len(weekly_trend[week_key])
        sentiment_trend.append({"week": week_key, "avg": round(3 + (avg_s * 2), 2)})

    return {
        "metadata": {"total_reviews": total_reviews},
        "kpis": {"average_rating": avg_rating, "reputation_score": max(0.0, 100 - risk_pct)},
        "visualizations": {
            "emotions": {e: round(sum(scores)/len(scores), 1) if scores else 0 for e, scores in emotion_accumulator.items()},
            "ratings": rating_distribution,
            "sentiment_trend": sentiment_trend
        },
        "risk": {
            "loss_probability": f"{risk_pct}%",
            "impact_level": "Critical" if risk_pct > 40 else "High" if risk_pct > 25 else "Medium" if risk_pct > 12 else "Low"
        }
    }

# ----------------------------------------------------------
# API Endpoints
# ----------------------------------------------------------
@router.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

@router.get("/ai/insights")
async def get_ai_insights(company_id: int = Query(...), start: Optional[str] = None, end: Optional[str] = None, session: AsyncSession = Depends(get_db)):
    start_dt, end_dt = safe_date(start), safe_date(end)
    stmt = select(Review).where(Review.company_id == company_id)
    if start_dt: stmt = stmt.where(Review.google_review_time >= start_dt)
    if end_dt: stmt = stmt.where(Review.google_review_time <= end_dt)
    
    result = await session.execute(stmt)
    return JSONResponse(content=compute_complete_analytics(result.scalars().all(), start_dt, end_dt))

@router.get("/revenue")
async def get_revenue_risk(company_id: int = Query(...), session: AsyncSession = Depends(get_db)):
    result = await session.execute(select(Review).where(Review.company_id == company_id))
    analytics = compute_complete_analytics(result.scalars().all())
    return {
        "risk_percent": analytics["risk"]["loss_probability"].replace("%", ""),
        "impact": analytics["risk"]["impact_level"],
        "reputation_score": analytics["kpis"]["reputation_score"]
    }

@router.get("/latest-reviews")
async def get_latest_reviews(company_id: int = Query(...), limit: int = 100, session: AsyncSession = Depends(get_db)):
    stmt = select(Review).where(Review.company_id == company_id).order_by(desc(Review.google_review_time)).limit(limit)
    result = await session.execute(stmt)
    return [{
        "rating": r.rating,
        "sentiment": get_sentiment_label(r.rating, r.sentiment_score),
        "review_text": r.text or "",
        "review_date": r.google_review_time.isoformat() if r.google_review_time else None,
        "source": "Google"
    } for r in result.scalars().all()]

@router.post("/chat")
async def chat_with_ai(request_data: dict, company_id: int = Query(...), session: AsyncSession = Depends(get_db)):
    user_msg = request_data.get("message", "").strip()
    company = await get_company(session, company_id)
    result = await session.execute(select(Review).where(Review.company_id == company_id).limit(10))
    reviews = result.scalars().all()
    
    context = f"Company: {company.name}. Recent Review: {reviews[0].text[:100] if reviews else 'No reviews'}."
    messages = [
        {"role": "system", "content": f"You are a business consultant. Context: {context}"},
        {"role": "user", "content": user_msg}
    ]
    return {"answer": await call_deepseek_api(messages)}

@router.get("/executive-report/pdf/{company_id}")
async def generate_executive_pdf(company_id: int, session: AsyncSession = Depends(get_db)):
    company = await get_company(session, company_id)
    result = await session.execute(select(Review).where(Review.company_id == company_id))
    analytics = compute_complete_analytics(result.scalars().all())
    
    def create_pdf():
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", "B", 16)
        pdf.cell(0, 10, sanitize_pdf(f"Report: {company.name}"), ln=True)
        pdf.set_font("Arial", "", 12)
        pdf.cell(0, 10, f"Avg Rating: {analytics['kpis']['average_rating']}", ln=True)
        pdf.cell(0, 10, f"Risk: {analytics['risk']['impact_level']}", ln=True)
        return pdf.output(dest="S")

    pdf_bytes = await asyncio.to_thread(create_pdf)
    return StreamingResponse(io.BytesIO(pdf_bytes), media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename=Report_{company_id}.pdf"})
