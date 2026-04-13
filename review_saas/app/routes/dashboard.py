# filename: app/routes/dashboard.py
# ==========================================================
# REVIEW INTELLIGENCE DASHBOARD — FULLY INTEGRATED
# ==========================================================
# Works with your database schema and DeepSeek API
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
from sqlalchemy import select, desc, func, and_
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
    "see", "look", "come", "went", "take", "make", "time", "day"
}

# Emotion keywords mapping
EMOTION_KEYWORDS = {
    "Joy": ["happy", "great", "amazing", "excellent", "fantastic", "wonderful", "love", "perfect", "awesome", "pleased", "satisfied", "delighted", "enjoy", "beautiful", "best", "nice"],
    "Anger": ["angry", "furious", "terrible", "awful", "horrible", "hate", "disgusting", "worst", "frustrated", "annoying", "useless", "waste", "mad", "upset"],
    "Sadness": ["sad", "disappointed", "unfortunate", "sorry", "regret", "depressing", "bad experience", "let down", "missed", "unhappy"],
    "Surprise": ["surprised", "unexpected", "shocked", "amazed", "astonished", "wow", "unbelievable", "remarkable", "stunning"],
    "Fear": ["worried", "concerned", "scared", "afraid", "nervous", "anxious", "fear", "terrified", "risky"],
    "Love": ["love", "adore", "cherish", "appreciate", "grateful", "thankful", "blessed", "heartwarming", "wonderful"]
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
    """Sanitize text for PDF generation"""
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
        scores[emotion] = min(count * 10, 100)
    
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
    """
    Compute ALL analytics needed by the frontend dashboard.
    """
    total_reviews = len(reviews)
    
    if total_reviews == 0:
        return {
            "metadata": {
                "total_reviews": 0,
                "recent_count": 0,
                "date_range": {
                    "start": start_date.isoformat() if start_date else None,
                    "end": end_date.isoformat() if end_date else None
                }
            },
            "kpis": {
                "average_rating": 0.0,
                "reputation_score": 100.0,
                "benchmark": {
                    "your_avg": 0.0,
                    "industry_avg": 4.2
                }
            },
            "visualizations": {
                "emotions": {"Joy": 0, "Anger": 0, "Sadness": 0, "Surprise": 0, "Fear": 0, "Love": 0},
                "ratings": {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0},
                "sentiment_trend": []
            },
            "risk": {
                "loss_probability": "0%",
                "impact_level": "Low",
                "reputation_score": 100.0
            },
            "top_keywords": [],
            "keyword_freq": []
        }
    
    ratings: List[int] = []
    rating_distribution = {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0}
    weekly_trend: Dict[str, List[float]] = defaultdict(list)
    emotion_accumulator: Dict[str, List[int]] = defaultdict(list)
    all_keywords: List[str] = []
    
    negative_count = 0
    severe_count = 0
    recent_count = 0
    thirty_days_ago = datetime.now() - timedelta(days=30)
    
    for review in reviews:
        if review.rating is not None:
            rating_val = int(review.rating)
            rating_distribution[str(rating_val)] = rating_distribution.get(str(rating_val), 0) + 1
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
            week_start = review.google_review_time - timedelta(days=review.google_review_time.weekday())
            week_key = week_start.strftime("%Y-%m-%d")
            
            if review.sentiment_score is not None:
                weekly_trend[week_key].append(review.sentiment_score)
            elif review.rating is not None:
                sent_score = (review.rating - 3) / 2
                weekly_trend[week_key].append(sent_score)
            
            if review.google_review_time >= thirty_days_ago:
                recent_count += 1
    
    avg_rating = round(sum(ratings) / len(ratings), 2) if ratings else 0.0
    avg_emotions = {emotion: round(sum(scores) / len(scores), 1) if scores else 0 
                    for emotion, scores in emotion_accumulator.items()}
    
    for emotion in EMOTION_KEYWORDS.keys():
        if emotion not in avg_emotions:
            avg_emotions[emotion] = 0
    
    sentiment_trend = []
    for week_key in sorted(weekly_trend.keys())[-12:]:
        scores = weekly_trend[week_key]
        avg_sent_score = sum(scores) / len(scores) if scores else 0
        avg_rating_from_sent = 3 + (avg_sent_score * 2)
        sentiment_trend.append({
            "week": week_key,
            "avg": round(avg_rating_from_sent, 2)
        })
    
    total = total_reviews
    raw_risk = (negative_count * 0.6 + severe_count * 0.4) / total if total > 0 else 0
    risk_pct = round(raw_risk * 100, 1)
    
    if risk_pct > 40: impact_level = "Critical"
    elif risk_pct > 25: impact_level = "High"
    elif risk_pct > 12: impact_level = "Medium"
    else: impact_level = "Low"
    
    reputation_score = max(0.0, round(100 - risk_pct, 1))
    keyword_counts = Counter(all_keywords)
    top_keywords = [word for word, _ in keyword_counts.most_common(10)]
    keyword_freq = [count for _, count in keyword_counts.most_common(10)]
    
    return {
        "metadata": {
            "total_reviews": total_reviews,
            "recent_count": recent_count,
            "date_range": {
                "start": start_date.isoformat() if start_date else None,
                "end": end_date.isoformat() if end_date else None
            }
        },
        "kpis": {
            "average_rating": avg_rating,
            "reputation_score": reputation_score,
            "benchmark": {
                "your_avg": avg_rating,
                "industry_avg": 4.2
            }
        },
        "visualizations": {
            "emotions": avg_emotions,
            "ratings": rating_distribution,
            "sentiment_trend": sentiment_trend
        },
        "risk": {
            "loss_probability": f"{risk_pct}%",
            "impact_level": impact_level,
            "reputation_score": reputation_score
        },
        "top_keywords": top_keywords,
        "keyword_freq": keyword_freq
    }

# ==========================================================
# API ENDPOINTS
# ==========================================================

@router.get("/ai/insights")
async def get_ai_insights(
    company_id: int = Query(..., description="Company ID to analyze"),
    start: Optional[str] = Query(None, description="Start date (ISO format)"),
    end: Optional[str] = Query(None, description="End date (ISO format)"),
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
        
        analytics = compute_complete_analytics(reviews, start_dt, end_dt)
        return JSONResponse(content=analytics)
    except Exception as e:
        logger.error(f"Error in get_ai_insights: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/revenue")
async def get_revenue_risk(
    company_id: int = Query(..., description="Company ID"),
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
    company_id: int = Query(..., description="Company ID"),
    limit: int = Query(100, ge=1, le=500, description="Number of reviews to return"),
    session: AsyncSession = Depends(get_db)
):
    try:
        await get_company(session, company_id)
        stmt = select(Review).where(Review.company_id == company_id).order_by(desc(Review.google_review_time)).limit(limit)
        result = await session.execute(stmt)
        reviews = result.scalars().all()
        formatted_reviews = [{
            "id": review.id,
            "rating": review.rating,
            "sentiment": get_sentiment_label(review.rating, review.sentiment_score),
            "review_text": review.text or "",
            "review_date": review.google_review_time.isoformat() if review.google_review_time else None,
            "author_name": review.author_name,
            "source": "Google"
        } for review in reviews]
        return JSONResponse(content=formatted_reviews)
    except Exception as e:
        logger.error(f"Error in get_latest_reviews: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/chat")
async def chat_with_ai(
    request_data: dict,
    company_id: int = Query(..., description="Company ID for context"),
    session: AsyncSession = Depends(get_db)
):
    try:
        user_message = request_data.get("message", "").strip()
        if not user_message: return {"answer": "Please enter a question."}
        
        company = await get_company(session, company_id)
        stmt = select(Review).where(Review.company_id == company_id).order_by(desc(Review.google_review_time)).limit(50)
        result = await session.execute(stmt)
        recent_reviews = result.scalars().all()
        analytics = compute_complete_analytics(recent_reviews)
        
        system_prompt = f"Expert Consultant for {company.name}. Avg Rating: {analytics['kpis']['average_rating']}. Score: {analytics['kpis']['reputation_score']}%."
        answer = await call_deepseek_api([{"role": "system", "content": system_prompt}, {"role": "user", "content": user_message}])
        return {"answer": answer}
    except Exception as e:
        logger.error(f"Error in chat_with_ai: {e}")
        return {"answer": "AI service unavailable."}

@router.get("/executive-report/pdf/{company_id}")
async def generate_executive_pdf(company_id: int, session: AsyncSession = Depends(get_db)):
    try:
        company = await get_company(session, company_id)
        stmt = select(Review).where(Review.company_id == company_id)
        result = await session.execute(stmt)
        reviews = result.scalars().all()
        analytics = compute_complete_analytics(reviews)
        
        def gen():
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Arial", "B", 16)
            pdf.cell(0, 10, sanitize_pdf(f"Report: {company.name}"), 1, 1, 'C')
            pdf.set_font("Arial", "", 12)
            pdf.cell(0, 10, f"Rating: {analytics['kpis']['average_rating']}", 0, 1)
            pdf.cell(0, 10, f"Score: {analytics['kpis']['reputation_score']}%", 0, 1)
            return pdf.output(dest="S")
            
        pdf_content = await asyncio.to_thread(gen)
        return StreamingResponse(io.BytesIO(pdf_content), media_type="application/pdf")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/sync-status/{company_id}")
async def get_sync_status(company_id: int, session: AsyncSession = Depends(get_db)):
    try:
        await get_company(session, company_id)
        latest_stmt = select(func.max(Review.google_review_time)).where(Review.company_id == company_id)
        latest_result = await session.execute(latest_stmt)
        latest_review_date = latest_result.scalar()
        count_stmt = select(func.count()).where(Review.company_id == company_id)
        count_result = await session.execute(count_stmt)
        return {
            "company_id": company_id,
            "latest_review_date": latest_review_date.isoformat() if latest_review_date else None,
            "total_reviews": count_result.scalar() or 0
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}
