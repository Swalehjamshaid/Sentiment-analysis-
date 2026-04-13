# filename: app/routes/dashboard.py
# ==========================================================
# REVIEW INTELLIGENCE DASHBOARD — FULLY INTEGRATED
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
# Prefix is set to /dashboard. Combined with /api in main.py, the final path is /api/dashboard/...
router = APIRouter(prefix="/dashboard", tags=["Dashboard"])
logger = logging.getLogger("dashboard")

# DeepSeek API Configuration
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"

# Sentiment thresholds
NEGATIVE_RATINGS = {1, 2}
NEG_SENTIMENT_LIMIT = -0.2
POS_SENTIMENT_LIMIT = 0.2

# Stopwords
STOPWORDS = {
    "the", "and", "with", "this", "that", "for", "from", "was", "were",
    "have", "has", "had", "very", "just", "they", "them", "their", "there",
    "but", "not", "are", "you", "your", "will", "can", "our", "all", "any"
}

# Emotion keywords
EMOTION_KEYWORDS = {
    "Joy": ["happy", "great", "amazing", "excellent", "fantastic", "wonderful", "love", "perfect", "awesome", "pleased", "satisfied", "delighted"],
    "Anger": ["angry", "furious", "terrible", "awful", "horrible", "hate", "disgusting", "worst", "frustrated", "annoying", "useless", "waste"],
    "Sadness": ["sad", "disappointed", "unfortunate", "sorry", "regret", "depressing", "bad experience", "let down", "missed"],
    "Surprise": ["surprised", "unexpected", "shocked", "amazed", "astonished", "wow", "unbelievable", "remarkable"],
    "Fear": ["worried", "concerned", "scared", "afraid", "nervous", "anxious", "fear", "terrified"],
    "Love": ["love", "adore", "cherish", "appreciate", "grateful", "thankful", "blessed", "heartwarming"]
}

# ----------------------------------------------------------
# Helper Functions
# ----------------------------------------------------------
def safe_date(val: str | None) -> datetime | None:
    """Convert ISO string to datetime safely."""
    if not val:
        return None
    try:
        return datetime.fromisoformat(val)
    except Exception:
        return None

def sanitize_pdf(text: str) -> str:
    """Sanitize text for FPDF latin-1 encoding."""
    if not text:
        return ""
    replacements = {
        "—": "-", "–": "-", "’": "'", "“": '"', "”": '"',
        "•": "-", "…": "...", "©": "(C)", "®": "(R)"
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
    return text.encode('latin-1', errors='ignore').decode('latin-1')

def extract_keywords(text: str) -> List[str]:
    """Extract keywords from review text."""
    if not text:
        return []
    words = []
    cleaned = re.sub(r'[^\w\s]', ' ', text.lower())
    for w in cleaned.split():
        if len(w) >= 4 and w.isalpha() and w not in STOPWORDS:
            words.append(w)
    return words

def compute_emotion_scores(text: str) -> Dict[str, int]:
    """Calculate intensity scores for different emotions based on keywords."""
    if not text:
        return {emotion: 0 for emotion in EMOTION_KEYWORDS}
    text_lower = text.lower()
    scores = {}
    for emotion, keywords in EMOTION_KEYWORDS.items():
        count = sum(1 for kw in keywords if kw in text_lower)
        scores[emotion] = min(count * 10, 100)
    return scores

def get_sentiment_label(rating: Optional[int], sentiment_score: Optional[float]) -> str:
    """Determine UI-friendly sentiment label."""
    if sentiment_score is not None:
        if sentiment_score <= NEG_SENTIMENT_LIMIT:
            return "negative"
        elif sentiment_score >= POS_SENTIMENT_LIMIT:
            return "positive"
        return "neutral"
    elif rating is not None:
        if rating <= 2:
            return "negative"
        elif rating >= 4:
            return "positive"
        return "neutral"
    return "neutral"

async def get_company(session: AsyncSession, company_id: int) -> Company:
    """Fetch company or raise 404."""
    result = await session.execute(select(Company).where(Company.id == company_id))
    company = result.scalars().first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return company

async def call_deepseek_api(messages: List[Dict]) -> str:
    """Interface with DeepSeek Chat API."""
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
            return "🔧 AI service temporarily unavailable."

# ----------------------------------------------------------
# Core Analytics Engine
# ----------------------------------------------------------
def compute_complete_analytics(reviews: List[Review]) -> Dict[str, Any]:
    """Generates the full data structure for the frontend dashboard."""
    total_reviews = len(reviews)
    
    if total_reviews == 0:
        return {
            "metadata": {"total_reviews": 0, "recent_count": 0},
            "kpis": {"average_rating": 0.0, "reputation_score": 100.0},
            "visualizations": {
                "emotions": {"Joy": 0, "Anger": 0, "Sadness": 0, "Surprise": 0, "Fear": 0, "Love": 0},
                "ratings": {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0},
                "sentiment_trend": []
            },
            "risk": {"loss_probability": "0%", "impact_level": "Low", "reputation_score": 100.0},
            "top_keywords": []
        }
    
    ratings = []
    rating_distribution = {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0}
    weekly_trend = {}
    emotion_accumulator = {emo: [] for emo in EMOTION_KEYWORDS}
    all_keywords = []
    negative_count = 0
    severe_count = 0
    recent_count = 0
    thirty_days_ago = datetime.now() - timedelta(days=30)
    
    for review in reviews:
        if review.rating is not None:
            rating_val = int(review.rating)
            rating_distribution[str(rating_val)] += 1
            ratings.append(rating_val)
            if rating_val in NEGATIVE_RATINGS:
                severe_count += 1
        
        if review.sentiment_score is not None:
            if review.sentiment_score <= NEG_SENTIMENT_LIMIT:
                negative_count += 1
        
        if review.text:
            emotions = compute_emotion_scores(review.text)
            for emotion, score in emotions.items():
                emotion_accumulator[emotion].append(score)
            all_keywords.extend(extract_keywords(review.text))
        
        if review.google_review_time:
            week_key = review.google_review_time.strftime("%Y-%m-%d")
            if week_key not in weekly_trend:
                weekly_trend[week_key] = []
            if review.sentiment_score is not None:
                weekly_trend[week_key].append(review.sentiment_score)
            elif review.rating is not None:
                weekly_trend[week_key].append((review.rating - 3) / 2)
            
            if review.google_review_time >= thirty_days_ago:
                recent_count += 1
    
    avg_rating = round(sum(ratings) / len(ratings), 2) if ratings else 0.0
    
    avg_emotions = {emo: round(sum(scores)/len(scores), 1) if scores else 0 
                   for emo, scores in emotion_accumulator.items()}
    
    sentiment_trend = []
    for week_key in sorted(weekly_trend.keys())[-12:]:
        scores = weekly_trend[week_key]
        avg_sent_score = sum(scores) / len(scores) if scores else 0
        sentiment_trend.append({
            "week": week_key,
            "avg": round(3 + (avg_sent_score * 2), 2)
        })
    
    raw_risk = (negative_count * 0.6 + severe_count * 0.4) / total_reviews if total_reviews > 0 else 0
    risk_pct = round(raw_risk * 100, 1)
    
    if risk_pct > 40: impact_level = "Critical"
    elif risk_pct > 25: impact_level = "High"
    elif risk_pct > 12: impact_level = "Medium"
    else: impact_level = "Low"
    
    reputation_score = max(0.0, round(100 - risk_pct, 1))
    keyword_counts = Counter(all_keywords)
    top_keywords = [word for word, _ in keyword_counts.most_common(10)]
    
    return {
        "metadata": {"total_reviews": total_reviews, "recent_count": recent_count},
        "kpis": {"average_rating": avg_rating, "reputation_score": reputation_score},
        "visualizations": {
            "emotions": avg_emotions,
            "ratings": rating_distribution,
            "sentiment_trend": sentiment_trend
        },
        "risk": {"loss_probability": f"{risk_pct}%", "impact_level": impact_level, "reputation_score": reputation_score},
        "top_keywords": top_keywords
    }

# ==========================================================
# API ENDPOINTS
# ==========================================================

@router.get("/ai/insights")
async def get_ai_insights(
    company_id: int = Query(...),
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_db)
):
    try:
        await get_company(session, company_id)
        start_dt = safe_date(start) if start else None
        end_dt = safe_date(end) if end else None
        
        stmt = select(Review).where(Review.company_id == company_id)
        if start_dt: stmt = stmt.where(Review.google_review_time >= start_dt)
        if end_dt: stmt = stmt.where(Review.google_review_time <= end_dt)
        
        result = await session.execute(stmt)
        reviews = result.scalars().all()
        analytics = compute_complete_analytics(reviews)
        return JSONResponse(content=analytics)
    except Exception as e:
        logger.error(f"Error in get_ai_insights: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/revenue")
async def get_revenue_risk(
    company_id: int = Query(...),
    session: AsyncSession = Depends(get_db)
):
    try:
        await get_company(session, company_id)
        stmt = select(Review).where(Review.company_id == company_id)
        result = await session.execute(stmt)
        reviews = result.scalars().all()
        analytics = compute_complete_analytics(reviews)
        return {
            "risk_percent": analytics["risk"]["loss_probability"].replace("%", ""),
            "impact": analytics["risk"]["impact_level"],
            "reputation_score": analytics["kpis"]["reputation_score"]
        }
    except Exception as e:
        logger.error(f"Error in get_revenue_risk: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/latest-reviews")
async def get_latest_reviews(
    company_id: int = Query(...),
    limit: int = Query(100, ge=1, le=500),
    session: AsyncSession = Depends(get_db)
):
    try:
        await get_company(session, company_id)
        stmt = (
            select(Review)
            .where(Review.company_id == company_id)
            .order_by(desc(Review.google_review_time))
            .limit(limit)
        )
        result = await session.execute(stmt)
        reviews = result.scalars().all()
        
        formatted_reviews = []
        for review in reviews:
            formatted_reviews.append({
                "id": review.id,
                "rating": review.rating,
                "sentiment": get_sentiment_label(review.rating, review.sentiment_score),
                "review_text": review.text or "",
                "review_date": review.google_review_time.isoformat() if review.google_review_time else None,
                "author_name": review.author_name,
                "source": "Google"
            })
        return JSONResponse(content=formatted_reviews)
    except Exception as e:
        logger.error(f"Error in get_latest_reviews: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/chat")
async def chat_with_ai(
    request_data: dict,
    company_id: int = Query(...),
    session: AsyncSession = Depends(get_db)
):
    try:
        user_message = request_data.get("message", "").strip()
        if not user_message:
            return {"answer": "Please enter a question about your business."}
        
        company = await get_company(session, company_id)
        stmt = select(Review).where(Review.company_id == company_id).order_by(desc(Review.google_review_time)).limit(50)
        result = await session.execute(stmt)
        recent_reviews = result.scalars().all()
        analytics = compute_complete_analytics(recent_reviews)
        
        system_prompt = f"""You are an expert Strategy Consultant for {company.name}. 
        Company Stats: Avg Rating {analytics['kpis']['average_rating']}/5, Score {analytics['kpis']['reputation_score']}%. 
        Top customer keywords: {', '.join(analytics['top_keywords'])}.
        Provide data-driven, actionable advice to help the business owner grow."""

        answer = await call_deepseek_api([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ])
        return {"answer": answer}
    except Exception as e:
        logger.error(f"Error in chat_with_ai: {e}")
        return {"answer": "I'm having trouble connecting to my strategist engine. Please try again soon."}

@router.get("/executive-report/pdf/{company_id}")
async def generate_executive_pdf(
    company_id: int,
    session: AsyncSession = Depends(get_db)
):
    try:
        company = await get_company(session, company_id)
        stmt = select(Review).where(Review.company_id == company_id)
        result = await session.execute(stmt)
        reviews = result.scalars().all()
        analytics = compute_complete_analytics(reviews)
        
        def generate_pdf() -> bytes:
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Arial", "B", 18)
            pdf.cell(0, 15, sanitize_pdf(f"Executive Report: {company.name}"), ln=True, align="C")
            pdf.ln(5)
            pdf.set_font("Arial", "B", 14)
            pdf.cell(0, 10, "Summary Metrics", ln=True)
            pdf.set_font("Arial", "", 12)
            pdf.cell(0, 8, f"Average Rating: {analytics['kpis']['average_rating']} / 5.0", ln=True)
            pdf.cell(0, 8, f"Reputation Score: {analytics['kpis']['reputation_score']}%", ln=True)
            pdf.cell(0, 8, f"Risk Level: {analytics['risk']['impact_level']}", ln=True)
            return pdf.output(dest="S")
        
        pdf_content = await asyncio.to_thread(generate_pdf)
        return StreamingResponse(
            io.BytesIO(pdf_content), 
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=Report_{company.name}.pdf"}
        )
    except Exception as e:
        logger.error(f"Error in generate_executive_pdf: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/health")
async def health_check():
    return {"status": "healthy", "deepseek_configured": bool(DEEPSEEK_API_KEY)}
