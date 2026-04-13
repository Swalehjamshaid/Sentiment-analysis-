# filename: app/routes/dashboard.py
# ==========================================================
# REVIEW INTELLIGENCE DASHBOARD — 100% FRONTEND INTEGRATION
# ==========================================================
# Supports ALL frontend attributes:
# - KPIs: Total Reviews, Avg Rating, Reputation Score
# - Emotion Radar Chart (6 emotions)
# - Sentiment Trend Line Chart
# - Rating Distribution Bar Chart
# - Latest 100 Reviews Table (with sentiment badges)
# - Revenue Risk Monitoring (Loss Probability, Impact Level)
# - AI Chat with DeepSeek API
# - Executive PDF Report
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

# DeepSeek API Configuration (using Railway env variable)
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

# Emotion keywords mapping for enhanced sentiment analysis
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
    text = text.encode('latin-1', errors='ignore').decode('latin-1')
    return text

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
        return "⚠️ DeepSeek API key not configured. Please add DEEPSEEK_API_KEY to your environment variables."
    
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
        except httpx.TimeoutException:
            logger.error("DeepSeek API timeout")
            return "⏰ The AI service is taking too long to respond. Please try again."
        except Exception as e:
            logger.error(f"DeepSeek API error: {e}")
            return "🔧 AI service is temporarily unavailable. Please try again later."

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
    Returns a complete object matching frontend expectations.
    """
    total_reviews = len(reviews)
    
    # Empty state
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
    
    # Initialize accumulators
    ratings: List[int] = []
    rating_distribution = {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0}
    weekly_trend: Dict[str, List[float]] = defaultdict(list)
    emotion_accumulator: Dict[str, List[int]] = defaultdict(list)
    all_keywords: List[str] = []
    
    # Counters for risk calculation
    negative_count = 0
    severe_count = 0
    recent_count = 0
    thirty_days_ago = datetime.now() - timedelta(days=30)
    
    for review in reviews:
        # Rating processing
        if review.rating is not None:
            rating_val = int(review.rating)
            rating_distribution[str(rating_val)] += 1
            ratings.append(rating_val)
            
            if rating_val in NEGATIVE_RATINGS:
                severe_count += 1
        
        # Sentiment processing
        if review.sentiment_score is not None:
            if review.sentiment_score <= NEG_SENTIMENT_LIMIT:
                negative_count += 1
        
        # Emotion analysis from review text
        if review.text:
            emotions = compute_emotion_scores(review.text)
            for emotion, score in emotions.items():
                emotion_accumulator[emotion].append(score)
            all_keywords.extend(extract_keywords(review.text))
        
        # Weekly trend
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
    
    # Calculate averages
    avg_rating = round(sum(ratings) / len(ratings), 2) if ratings else 0.0
    
    # Average emotion scores
    avg_emotions = {}
    for emotion, scores in emotion_accumulator.items():
        avg_emotions[emotion] = round(sum(scores) / len(scores), 1) if scores else 0
    
    for emotion in EMOTION_KEYWORDS.keys():
        if emotion not in avg_emotions:
            avg_emotions[emotion] = 0
    
    # Build sentiment trend
    sentiment_trend = []
    for week_key in sorted(weekly_trend.keys()):
        scores = weekly_trend[week_key]
        avg_sent_score = sum(scores) / len(scores) if scores else 0
        avg_rating_from_sent = 3 + (avg_sent_score * 2)
        sentiment_trend.append({
            "week": week_key,
            "avg": round(avg_rating_from_sent, 2)
        })
    
    # Calculate risk
    total = total_reviews
    raw_risk = (negative_count * 0.6 + severe_count * 0.4) / total if total > 0 else 0
    risk_pct = round(raw_risk * 100, 1)
    
    if risk_pct > 40:
        impact_level = "Critical"
    elif risk_pct > 25:
        impact_level = "High"
    elif risk_pct > 12:
        impact_level = "Medium"
    else:
        impact_level = "Low"
    
    reputation_score = max(0.0, round(100 - risk_pct, 1))
    
    # Top keywords
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
# API ENDPOINTS - 100% Frontend Compatible
# ==========================================================

@router.get("/ai/insights")
async def get_ai_insights(
    company_id: int = Query(..., description="Company ID to analyze"),
    start: Optional[str] = Query(None, description="Start date (ISO format)"),
    end: Optional[str] = Query(None, description="End date (ISO format)"),
    session: AsyncSession = Depends(get_db)
):
    """MAIN INSIGHTS ENDPOINT - Returns all data for KPIs, visualizations, and risk metrics"""
    await get_company(session, company_id)
    
    start_dt = safe_date(start) if start else None
    end_dt = safe_date(end) if end else None
    
    stmt = select(Review).where(Review.company_id == company_id)
    if start_dt:
        stmt = stmt.where(Review.google_review_time >= start_dt)
    if end_dt:
        stmt = stmt.where(Review.google_review_time <= end_dt)
    
    result = await session.execute(stmt)
    reviews = result.scalars().all()
    
    analytics = compute_complete_analytics(reviews, start_dt, end_dt)
    return JSONResponse(content=analytics)

@router.get("/revenue")
async def get_revenue_risk(
    company_id: int = Query(..., description="Company ID"),
    session: AsyncSession = Depends(get_db)
):
    """REVENUE RISK MONITORING - Used by the risk card in frontend"""
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

@router.get("/latest-reviews")
async def get_latest_reviews(
    company_id: int = Query(..., description="Company ID"),
    limit: int = Query(100, ge=1, le=500, description="Number of reviews to return"),
    session: AsyncSession = Depends(get_db)
):
    """
    LATEST REVIEWS TABLE ENDPOINT
    Returns the most recent reviews for the DataTable in frontend.
    This is the key endpoint for the "Latest 100 Reviews" table.
    """
    await get_company(session, company_id)
    
    stmt = (
        select(Review)
        .where(Review.company_id == company_id)
        .order_by(desc(Review.google_review_time))
        .limit(limit)
    )
    result = await session.execute(stmt)
    reviews = result.scalars().all()
    
    # Format reviews for frontend DataTable
    formatted_reviews = []
    for review in reviews:
        sentiment_label = get_sentiment_label(review.rating, review.sentiment_score)
        
        formatted_reviews.append({
            "id": review.id,
            "rating": review.rating,
            "sentiment": sentiment_label,
            "review_text": review.text or review.review_text or "",
            "review_date": review.google_review_time.isoformat() if review.google_review_time else None,
            "author_name": review.author_name,
            "source": "Google"
        })
    
    return JSONResponse(content=formatted_reviews)

@router.post("/chat")
async def chat_with_ai(
    request_data: dict,
    company_id: int = Query(..., description="Company ID for context"),
    session: AsyncSession = Depends(get_db)
):
    """AI CHAT ENDPOINT for Strategy Consultant widget - Uses DeepSeek API"""
    user_message = request_data.get("message", "").strip()
    if not user_message:
        return {"answer": "Please enter a question about your business reviews."}
    
    company = await get_company(session, company_id)
    
    stmt = (
        select(Review)
        .where(Review.company_id == company_id)
        .order_by(desc(Review.google_review_time))
        .limit(50)
    )
    result = await session.execute(stmt)
    recent_reviews = result.scalars().all()
    
    analytics = compute_complete_analytics(recent_reviews)
    
    # Prepare review snippets for AI context
    review_snippets = []
    for review in recent_reviews[:10]:
        if review.text:
            snippet = f"Rating {review.rating}/5: {review.text[:200]}"
            review_snippets.append(snippet)
    
    system_prompt = f"""You are an expert Business Strategy Consultant specializing in customer review analysis and reputation management.

COMPANY CONTEXT:
- Name: {company.name}
- Total Reviews Analyzed: {analytics['metadata']['total_reviews']}
- Average Rating: {analytics['kpis']['average_rating']}/5
- Reputation Score: {analytics['kpis']['reputation_score']}%
- Risk Level: {analytics['risk']['impact_level']}
- Loss Probability: {analytics['risk']['loss_probability']}

RECENT REVIEW SAMPLES:
{chr(10).join(review_snippets[:5])}

INSTRUCTIONS:
- Provide actionable, data-driven advice
- Keep responses concise (2-4 sentences)
- Focus on operational improvements, customer satisfaction, and revenue protection
- Be professional and helpful"""
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message}
    ]
    
    answer = await call_deepseek_api(messages)
    return {"answer": answer}

@router.get("/executive-report/pdf/{company_id}")
async def generate_executive_pdf(
    company_id: int,
    session: AsyncSession = Depends(get_db)
):
    """PDF REPORT ENDPOINT - Generates downloadable executive summary"""
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
        
        pdf.set_font("Arial", "", 10)
        pdf.cell(0, 8, f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", ln=True, align="R")
        pdf.ln(5)
        
        pdf.set_font("Arial", "B", 14)
        pdf.cell(0, 10, "Key Performance Indicators", ln=True)
        pdf.set_font("Arial", "", 11)
        pdf.cell(0, 8, f"Total Reviews Analyzed: {analytics['metadata']['total_reviews']}", ln=True)
        pdf.cell(0, 8, f"Average Rating: {analytics['kpis']['average_rating']} / 5.0", ln=True)
        pdf.cell(0, 8, f"Reputation Score: {analytics['kpis']['reputation_score']}%", ln=True)
        pdf.ln(5)
        
        pdf.set_font("Arial", "B", 14)
        pdf.cell(0, 10, "Risk Assessment", ln=True)
        pdf.set_font("Arial", "", 11)
        pdf.cell(0, 8, f"Loss Probability: {analytics['risk']['loss_probability']}", ln=True)
        pdf.cell(0, 8, f"Impact Level: {analytics['risk']['impact_level']}", ln=True)
        pdf.ln(5)
        
        pdf.set_font("Arial", "B", 14)
        pdf.cell(0, 10, "Rating Distribution", ln=True)
        pdf.set_font("Arial", "", 11)
        ratings = analytics['visualizations']['ratings']
        for star in range(1, 6):
            count = ratings.get(str(star), 0)
            pct = (count / analytics['metadata']['total_reviews'] * 100) if analytics['metadata']['total_reviews'] > 0 else 0
            pdf.cell(0, 8, f"{star}★: {count} reviews ({pct:.1f}%)", ln=True)
        
        return pdf.output(dest="S")
    
    pdf_content = await asyncio.to_thread(generate_pdf)
    return StreamingResponse(
        io.BytesIO(pdf_content),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=Review_Report_{company.name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        }
    )

@router.get("/sync-status/{company_id}")
async def get_sync_status(
    company_id: int,
    session: AsyncSession = Depends(get_db)
):
    """SYNC STATUS ENDPOINT - Returns information about when reviews were last synced"""
    await get_company(session, company_id)
    
    latest_stmt = select(func.max(Review.google_review_time)).where(Review.company_id == company_id)
    latest_result = await session.execute(latest_stmt)
    latest_review_date = latest_result.scalar()
    
    count_stmt = select(func.count()).where(Review.company_id == company_id)
    count_result = await session.execute(count_stmt)
    total_reviews = count_result.scalar()
    
    return {
        "company_id": company_id,
        "latest_review_date": latest_review_date.isoformat() if latest_review_date else None,
        "total_reviews": total_reviews or 0,
        "sync_required": latest_review_date is None or (datetime.now() - latest_review_date).days > 7
    }

@router.get("/health")
async def health_check():
    """Simple health check endpoint"""
    return {
        "status": "healthy",
        "deepseek_configured": bool(DEEPSEEK_API_KEY),
        "timestamp": datetime.now().isoformat()
    }
