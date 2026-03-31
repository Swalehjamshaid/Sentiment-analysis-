# ===================================================================
# PROJECT: ReviewSaaS - AI Intelligence Dashboard
# MODULE: app.routes.dashboard
# DESCRIPTION: Final Integrated Backend for dashboard.html
# ===================================================================

from __future__ import annotations
import logging
import re
from io import BytesIO
from collections import defaultdict, deque, Counter
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional

from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from app.core.db import get_session
from app.core.models import Review
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import LETTER
from reportlab.lib import colors

# Initialize Router with the prefix expected by the HTML
router = APIRouter(prefix="/dashboard", tags=["dashboard"])
logger = logging.getLogger("ReviewSaaS.Dashboard")

# AI Chatbot Memory
CHAT_MEMORY: Dict[int, List[Dict[str, str]]] = {}

def remember(company_id: int, role: str, message: str):
    if company_id not in CHAT_MEMORY:
        CHAT_MEMORY[company_id] = []
    CHAT_MEMORY[company_id].append({"role": role, "message": message})
    if len(CHAT_MEMORY[company_id]) > 10:
        CHAT_MEMORY[company_id].pop(0)

class AnalyticsEngine:
    """Core logic to process review data into dashboard-ready formats."""
    
    @staticmethod
    def calculate_nps(reviews: List[Review]) -> int:
        total = len(reviews)
        if total == 0: return 0
        promoters = len([r for r in reviews if r.rating >= 5])
        detractors = len([r for r in reviews if r.rating <= 3])
        return int(((promoters - detractors) / total) * 100)

    @staticmethod
    def extract_keywords(reviews: List[Review]) -> List[Dict[str, Any]]:
        text_data = " ".join([(r.text or "").lower() for r in reviews])
        words = re.findall(r'\b[a-z]{5,}\b', text_data)
        stop_words = {'about', 'there', 'their', 'would', 'really', 'place', 'service', 'great'}
        filtered = [w for w in words if w not in stop_words]
        return [{"text": k, "value": v} for k, v in Counter(filtered).most_common(12)]

def compute_dashboard_data(reviews: List[Review]):
    total = len(reviews)
    if total == 0: return None

    emotions = {"Positive": 0, "Neutral": 0, "Negative": 0}
    rating_dist = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    daily_logs = defaultdict(list)

    for r in reviews:
        # Distribution
        curr_rating = r.rating or 0
        if curr_rating in rating_dist: rating_dist[curr_rating] += 1
        
        # Emotions/Sentiment
        score = r.sentiment_score or 0.0
        if score >= 0.25: emotions["Positive"] += 1
        elif score <= -0.25: emotions["Negative"] += 1
        else: emotions["Neutral"] += 1

        # Trend logic
        time_ref = r.google_review_time or r.first_seen_at
        if time_ref:
            daily_logs[time_ref.strftime("%Y-%m-%d")].append(curr_rating)

    # Calculate 7-day moving average trend
    trend_data = []
    moving_window = deque(maxlen=7)
    for d in sorted(daily_logs):
        day_avg = sum(daily_logs[d]) / len(daily_logs[d])
        moving_window.append(day_avg)
        trend_data.append({"week": d, "avg": round(sum(moving_window) / len(moving_window), 2)})

    avg_rating = round(sum(r.rating for r in reviews) / total, 2)
    
    return {
        "metadata": {"total_reviews": total},
        "kpis": {
            "average_rating": avg_rating,
            "reputation_score": AnalyticsEngine.calculate_nps(reviews)
        },
        "visualizations": {
            "ratings": rating_dist,
            "emotions": emotions,
            "sentiment_trend": trend_data,
            "keywords": AnalyticsEngine.extract_keywords(reviews)
        }
    }

# -------------------------------------------------------------------
# ENDPOINTS (Aligned with HTML Fetch calls)
# -------------------------------------------------------------------

@router.get("/ai/insights")
async def get_insights(
    company_id: int = Query(...), 
    start: str = Query(...), 
    end: str = Query(...), 
    session: AsyncSession = Depends(get_session)
):
    """Handles the 'Analyze Business' button click."""
    try:
        # Handle both standard date and ISO string formats from browser
        start_dt = datetime.fromisoformat(start.replace('Z', '+00:00'))
        end_dt = datetime.fromisoformat(end.replace('Z', '+00:00'))
    except ValueError:
        return _empty_dashboard()

    stmt = select(Review).where(
        and_(
            Review.company_id == company_id,
            Review.google_review_time >= start_dt,
            Review.google_review_time <= end_dt
        )
    )
    
    result = await session.execute(stmt)
    reviews = result.scalars().all()
    
    data = compute_dashboard_data(reviews)
    return data if data else _empty_dashboard()

@router.get("/revenue")
async def get_revenue_risk(company_id: int, session: AsyncSession = Depends(get_session)):
    """Calculates the Risk Cards data."""
    res = await session.execute(
        select(func.avg(Review.rating)).where(Review.company_id == company_id)
    )
    avg = res.scalar() or 0
    
    risk_pct = 85 if avg < 3.0 else (45 if avg < 4.0 else 15)
    impact = "High" if risk_pct > 50 else "Low"
    
    return {"risk_percent": risk_pct, "impact": impact}

@router.get("/chatbot/explain/{company_id}")
async def explain_data(company_id: int, question: str, session: AsyncSession = Depends(get_session)):
    """AI Strategy Consultant logic."""
    stmt = select(Review).where(Review.company_id == company_id)
    res = await session.execute(stmt)
    reviews = res.scalars().all()
    
    data = compute_dashboard_data(reviews)
    
    # Simple logic-based response (Replace with LLM call if integrated)
    if not data:
        answer = "I don't have enough data for this business to provide a strategy."
    else:
        avg = data['kpis']['average_rating']
        if avg < 3.5:
            answer = f"Your rating is {avg}. I recommend focusing on your 'Negative' emotions (radar chart) to identify service gaps."
        else:
            answer = f"With a {avg} rating, your business is performing well. Use the keywords cloud to see what customers love most."

    remember(company_id, "user", question)
    remember(company_id, "ai", answer)
    return {"answer": answer}

@router.get("/executive-report/pdf/{company_id}")
async def download_pdf(company_id: int, session: AsyncSession = Depends(get_session)):
    """Generates the Report PDF."""
    stmt = select(Review).where(Review.company_id == company_id)
    res = await session.execute(stmt)
    reviews = res.scalars().all()
    data = compute_dashboard_data(reviews)

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=LETTER)
    
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(100, 750, f"Executive Summary: Company #{company_id}")
    
    pdf.setFont("Helvetica", 12)
    if data:
        pdf.drawString(100, 720, f"Average Rating: {data['kpis']['average_rating']}")
        pdf.drawString(100, 700, f"Total Reviews Analyzed: {data['metadata']['total_reviews']}")
        pdf.drawString(100, 680, f"Reputation (NPS) Score: {data['kpis']['reputation_score']}")
    else:
        pdf.drawString(100, 720, "No data available for this report.")

    pdf.save()
    buffer.seek(0)
    
    return StreamingResponse(
        buffer, 
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=Report_Company_{company_id}.pdf"}
    )

def _empty_dashboard():
    """Fallback for when no reviews are found."""
    return JSONResponse({
        "metadata": {"total_reviews": 0},
        "kpis": {"average_rating": 0, "reputation_score": 0},
        "visualizations": {
            "ratings": {1:0, 2:0, 3:0, 4:0, 5:0},
            "emotions": {"Positive": 0, "Neutral": 0, "Negative": 0},
            "sentiment_trend": [],
            "keywords": []
        }
    })
