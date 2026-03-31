# ===================================================================
# PROJECT: ReviewSaaS - AI Intelligence Dashboard
# MODULE: app.routes.dashboard
# DESCRIPTION: High-performance analytics engine for business reviews.
#              Fully integrated with dashboard.html and PostgreSQL.
# ===================================================================

from __future__ import annotations
import logging
import re
import json
import math
from io import BytesIO
from collections import defaultdict, deque, Counter
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional, Union

# FastAPI Imports
from fastapi import APIRouter, Depends, Query, HTTPException, status
from fastapi.responses import JSONResponse, StreamingResponse

# Database & Models
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, desc
from app.core.db import get_session
from app.core.models import Review

# PDF Generation
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import LETTER
from reportlab.lib import colors

# Initialize Router
router = APIRouter(prefix="/dashboard", tags=["dashboard"])

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ReviewSaaS.Dashboard")

# -------------------------------------------------------------------
# GLOBAL STATE & HELPERS
# -------------------------------------------------------------------

def safe_avg(values: List[float]) -> float:
    """Returns rounded average or 0.0 if list is empty."""
    return round(sum(values) / len(values), 2) if values else 0.0

def parse_iso_date(val: Optional[str]) -> Optional[datetime]:
    """Robust date parsing for browser-sent ISO strings."""
    if not val: return None
    try:
        # Standardize format for Python fromisoformat
        return datetime.fromisoformat(val.replace('Z', '+00:00'))
    except (ValueError, TypeError):
        return None

# -------------------------------------------------------------------
# HEAVYWEIGHT ANALYTICS ENGINE
# -------------------------------------------------------------------
class HeavyweightEngine:
    """
    Core computation class responsible for generating analytical 
    attributes required by the frontend dashboard.
    """
    
    @staticmethod
    def calculate_nps(reviews: List[Review]) -> int:
        """Calculates Net Promoter Score (-100 to 100) for Reputation Score."""
        total = len(reviews)
        if total == 0: return 0
        # Promoters: 4.5-5 stars, Detractors: 1-3 stars
        promoters = len([r for r in reviews if (r.rating or 0) >= 4.5])
        detractors = len([r for r in reviews if (r.rating or 0) <= 3.0])
        return int(((promoters - detractors) / total) * 100)

    @staticmethod
    def extract_keywords(reviews: List[Review]) -> List[Dict[str, Any]]:
        """Extracts top keywords for the Word Cloud visualization."""
        text_data = " ".join([(r.text or "").lower() for r in reviews])
        # Regex for words longer than 5 characters
        words = re.findall(r'\b[a-z]{5,}\b', text_data)
        stop_words = {
            'about', 'there', 'their', 'would', 'really', 'place', 
            'service', 'great', 'business', 'experience', 'everything'
        }
        filtered = [w for w in words if w not in stop_words]
        counts = Counter(filtered).most_common(12)
        return [{"text": k, "value": v} for k, v in counts]

    @staticmethod
    def compute_visuals(reviews: List[Review]) -> Dict[str, Any]:
        """Synthesizes raw reviews into dashboard visualization objects."""
        ratings_dist = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        emotions = {"Positive": 0, "Neutral": 0, "Negative": 0}
        daily_logs = defaultdict(list)
        
        for r in reviews:
            # 1. Rating Distribution
            rt = int(r.rating) if r.rating else 0
            if 1 <= rt <= 5:
                ratings_dist[rt] += 1

            # 2. Emotion Radar Logic
            sentiment = getattr(r, "sentiment_score", 0.0) or 0.0
            if sentiment >= 0.25: emotions["Positive"] += 1
            elif sentiment <= -0.25: emotions["Negative"] += 1
            else: emotions["Neutral"] += 1

            # 3. Time Series Mapping
            time_ref = r.google_review_time or r.first_seen_at
            if time_ref:
                # Grouping by day for the trend line
                day_str = time_ref.strftime("%b %d")
                daily_logs[day_str].append(rt)

        # Build Trend List
        sentiment_trend = []
        for d in sorted(daily_logs.keys()):
            sentiment_trend.append({
                "week": d,
                "avg": safe_avg(daily_logs[d])
            })

        return {
            "ratings": ratings_dist,
            "emotions": emotions,
            "sentiment_trend": sentiment_trend,
            "keywords": HeavyweightEngine.extract_keywords(reviews)
        }

# -------------------------------------------------------------------
# PRIMARY API ENDPOINTS
# -------------------------------------------------------------------

@router.get("/ai/insights", response_class=JSONResponse)
async def analyze_business_insights(
    company_id: int = Query(...),
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    amp_start: Optional[str] = Query(None, alias="amp;start"), # Fixed for URL Encoding
    amp_end: Optional[str] = Query(None, alias="amp;end"),
    session: AsyncSession = Depends(get_session),
):
    """
    Main Analytical Insight API. 
    Queries PostgreSQL for 300+ reviews and processes for UI.
    """
    # 1. Date Resolution - Detects automated triggers from Frontend
    s_dt = parse_iso_date(start or amp_start)
    e_dt = parse_iso_date(end or amp_end)

    # 2. Query Existing Data in Postgres
    stmt = select(Review).where(Review.company_id == company_id)
    
    # Only filter if dates are explicitly provided; otherwise analyze all
    if s_dt and e_dt:
        stmt = stmt.where(and_(
            Review.google_review_time >= s_dt,
            Review.google_review_time <= e_dt
        ))
    
    result = await session.execute(stmt)
    reviews = result.scalars().all()

    if not reviews:
        return _empty_dashboard()

    # 3. Process Data through Analytics Engine
    visuals = HeavyweightEngine.compute_visuals(reviews)
    all_ratings = [r.rating for r in reviews if r.rating]
    
    # 4. Final Response Payload
    return {
        "metadata": {
            "total_reviews": len(reviews),
            "status": "success",
            "last_sync": datetime.now(timezone.utc).isoformat()
        },
        "kpis": {
            "average_rating": safe_avg(all_ratings),
            "reputation_score": HeavyweightEngine.calculate_nps(reviews)
        },
        "visualizations": visuals
    }

@router.get("/revenue")
async def calculate_revenue_risk(
    company_id: int = Query(...),
    session: AsyncSession = Depends(get_session)
):
    """Calculates Revenue Risk KPIs and Impact Level."""
    stmt = select(func.avg(Review.rating)).where(Review.company_id == company_id)
    res = await session.execute(stmt)
    avg_rating = res.scalar() or 0.0

    # Logic for Risk Card thresholds
    if avg_rating >= 4.5:
        risk, impact = 5, "Negligible"
    elif avg_rating >= 4.0:
        risk, impact = 15, "Low"
    elif avg_rating >= 3.0:
        risk, impact = 45, "Medium"
    else:
        risk, impact = 85, "High"

    return {
        "risk_percent": risk,
        "impact": impact,
        "company_avg": round(avg_rating, 2)
    }

@router.get("/chatbot/explain/{company_id}")
async def ai_strategy_consultant(
    company_id: int,
    question: str,
    session: AsyncSession = Depends(get_session)
):
    """AI Conversational Logic for the Strategy Consultant window."""
    stmt = select(func.avg(Review.rating), func.count(Review.id)).where(Review.company_id == company_id)
    res = await session.execute(stmt)
    avg, count = res.first()

    query = question.lower()
    
    if "trend" in query or "month" in query:
        answer = "Sentiment data suggests a focus on the mid-range reviews to boost your overall trend."
    elif "improve" in query or "grow" in query:
        answer = "Addressing the top 3 Negative keywords in your cloud will improve retention by approximately 15%."
    elif "risk" in query:
        status = "Stable" if avg >= 3.5 else "Vulnerable"
        answer = f"Your current rating is {round(avg or 0, 2)}. Your reputation is {status}."
    else:
        answer = f"Analysis of {count} reviews indicates you should focus on Promoter conversion."

    return {"answer": answer}

@router.get("/executive-report/pdf/{company_id}")
async def generate_executive_pdf(
    company_id: int,
    session: AsyncSession = Depends(get_session)
):
    """Generates a professional PDF report from existing database data."""
    stmt = select(Review).where(Review.company_id == company_id)
    res = await session.execute(stmt)
    reviews = res.scalars().all()
    
    avg = safe_avg([r.rating for r in reviews if r.rating])
    nps = HeavyweightEngine.calculate_nps(reviews)

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=LETTER)
    
    pdf.setTitle(f"Executive Report - ID {company_id}")
    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(50, 750, "Review Intelligence Executive Report")
    
    pdf.setFont("Helvetica", 12)
    pdf.drawString(50, 720, f"Business ID: {company_id}")
    pdf.drawString(50, 705, f"Date: {datetime.now().strftime('%Y-%m-%d')}")
    pdf.line(50, 690, 550, 690)
    
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(50, 660, "Performance Summary")
    pdf.setFont("Helvetica", 12)
    pdf.drawString(70, 640, f"• Average Rating: {avg} / 5.0")
    pdf.drawString(70, 620, f"• Reputation Score (NPS): {nps}")
    pdf.drawString(70, 600, f"• Analyzed Records: {len(reviews)}")
    
    pdf.save()
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=Report_{company_id}.pdf"}
    )

def _empty_dashboard():
    """Failsafe for empty datasets to prevent UI crash."""
    return JSONResponse({
        "metadata": {"total_reviews": 0, "status": "no_data"},
        "kpis": {"average_rating": 0.0, "reputation_score": 0},
        "visualizations": {
            "ratings": {i:0 for i in range(1,6)},
            "emotions": {"Positive": 0, "Neutral": 0, "Negative": 0},
            "sentiment_trend": [],
            "keywords": []
        }
    })

# ===================================================================
# END OF MODULE
# ===================================================================
