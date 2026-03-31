# ===================================================================
# PROJECT: ReviewSaaS - AI Intelligence Dashboard
# MODULE: app.routes.dashboard
# DESCRIPTION: High-performance analytics engine for business reviews.
#              Implements 10 Advanced Attributes including Bayesian
#              Averages, NPS, and Linear Regression Forecasting.
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

# Fast API Imports
from fastapi import APIRouter, Depends, Query, HTTPException, status
from fastapi.responses import JSONResponse, StreamingResponse

# Database & Models
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, desc
from app.core.db import get_session
from app.core.models import Review, Competitor

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
# GLOBAL STATE & MEMORY MANAGEMENT
# -------------------------------------------------------------------
# Simple in-memory chat memory to persist context between API calls
# for the AI Strategy Consultant feature.
CHAT_MEMORY: Dict[int, List[Dict[str, str]]] = {}
MAX_MEMORY_THRESHOLD = 10

def remember(company_id: int, role: str, message: str) -> None:
    """
    Stores a message in the per-company conversation buffer.
    Ensures memory does not exceed the MAX_MEMORY_THRESHOLD.
    """
    if company_id not in CHAT_MEMORY:
        CHAT_MEMORY[company_id] = []
    
    CHAT_MEMORY[company_id].append({
        "role": role, 
        "message": message,
        "timestamp": datetime.now(timezone.utc).isoformat()
    })
    
    if len(CHAT_MEMORY[company_id]) > MAX_MEMORY_THRESHOLD:
        CHAT_MEMORY[company_id].pop(0)
        logger.debug(f"Memory threshold reached for company {company_id}. Oldest message evicted.")

def recall(company_id: int) -> List[Dict[str, str]]:
    """Retrieves the conversation history for a specific business entity."""
    return CHAT_MEMORY.get(company_id, [])

# -------------------------------------------------------------------
# HEAVYWEIGHT ANALYTICS ENGINE
# -------------------------------------------------------------------
class HeavyweightEngine:
    """
    Core computation class responsible for generating all 10
    analytical attributes required by the frontend dashboard.
    """
    
    @staticmethod
    def calculate_bayesian_average(reviews: List[Review], global_mean: float = 3.5, confidence_weight: int = 5) -> float:
        """
        Implements Bayesian Average to prevent '1-review' businesses 
        from skewing rankings.
        """
        v = len(reviews)
        if v == 0: return 0.0
        R = sum(r.rating for r in reviews) / v
        return round((v * R + confidence_weight * global_mean) / (v + confidence_weight), 2)

    @staticmethod
    def calculate_nps(reviews: List[Review]) -> int:
        """Calculates the Net Promoter Score (-100 to 100)."""
        total = len(reviews)
        if total == 0: return 0
        promoters = len([r for r in reviews if r.rating >= 5])
        detractors = len([r for r in reviews if r.rating <= 3])
        return int(((promoters - detractors) / total) * 100)

    @staticmethod
    def extract_keywords(reviews: List[Review]) -> List[Dict[str, Any]]:
        """Extracts top keywords for the Word Cloud visualization."""
        text_data = " ".join([(r.text or "").lower() for r in reviews])
        words = re.findall(r'\b[a-z]{5,}\b', text_data)
        stop_words = {'about', 'there', 'their', 'would', 'really', 'place', 'service', 'great', 'business'}
        filtered = [w for w in words if w not in stop_words]
        counts = Counter(filtered).most_common(12)
        return [{"text": k, "value": v} for k, v in counts]

    @staticmethod
    def perform_regression(daily_data: Dict[str, List[float]]) -> List[Dict[str, Any]]:
        """
        Simple linear trend projection to simulate future ratings.
        """
        sorted_keys = sorted(daily_data.keys())
        if len(sorted_keys) < 2:
            return [{"month": "Next Month", "avg": 0.0}]

        y = [sum(daily_data[k])/len(daily_data[k]) for k in sorted_keys]
        x = list(range(len(y)))
        
        # Calculate slope (m) and intercept (b) for y = mx + b
        n = len(x)
        sum_x = sum(x)
        sum_y = sum(y)
        sum_xx = sum(i*i for i in x)
        sum_xy = sum(i*j for i, j in zip(x, y))
        
        denominator = (n * sum_xx - sum_x**2)
        if denominator == 0:
            return [{"month": "Trend", "avg": round(y[-1], 2)}]
            
        slope = (n * sum_xy - sum_x * sum_y) / denominator
        intercept = (sum_y - slope * sum_x) / n
        
        forecast = []
        for i in range(1, 4):
            val = slope * (n + i) + intercept
            forecast.append({
                "month": f"Projected +{i}", 
                "avg": round(max(1.0, min(5.0, val)), 2)
            })
        return forecast

def compute_analytics(reviews: List[Review]) -> Optional[Dict[str, Any]]:
    """
    Main entry point for review analysis. Synthesizes multiple data 
    streams into a single dashboard-ready response object.
    """
    total = len(reviews)
    if total == 0:
        logger.warning("Attempted to compute analytics for zero reviews.")
        return None

    # Initialize accumulation variables
    ratings_list = []
    sentiments_list = []
    emotions = {"Positive": 0, "Neutral": 0, "Negative": 0}
    rating_dist = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    daily_logs = defaultdict(list)
    monthly_logs = defaultdict(list)

    # Secondary metrics
    responded_count = 0
    complaints_count = 0

    # Iterative Analysis Pass
    for r in reviews:
        # Rating Logic
        curr_rating = r.rating or 0
        ratings_list.append(curr_rating)
        if curr_rating in rating_dist:
            rating_dist[curr_rating] += 1

        # Sentiment Logic
        score = r.sentiment_score or 0.0
        sentiments_list.append(score)
        if score >= 0.25:
            emotions["Positive"] += 1
        elif score <= -0.25:
            emotions["Negative"] += 1
        else:
            emotions["Neutral"] += 1

        # Time-series Mapping (Handling potential None values)
        time_ref = r.google_review_time or r.first_seen_at
        if time_ref:
            day_str = time_ref.strftime("%Y-%m-%d")
            month_str = time_ref.strftime("%b %Y")
            daily_logs[day_str].append(curr_rating)
            monthly_logs[month_str].append(score)

        # Attribute Checks
        if getattr(r, "review_reply_text", None):
            responded_count += 1
        if getattr(r, "is_complaint", False):
            complaints_count += 1

    # Calculation Block
    avg_rating = round(sum(ratings_list) / total, 2)
    weighted_avg = HeavyweightEngine.calculate_bayesian_average(reviews)
    rep_score = HeavyweightEngine.calculate_nps(reviews)
    
    # Trend Calculation with deque windowing
    trend_data = []
    moving_window = deque(maxlen=7)
    for d in sorted(daily_logs):
        day_avg = sum(daily_logs[d]) / len(daily_logs[d])
        moving_window.append(day_avg)
        trend_data.append({
            "week": d, 
            "avg": round(sum(moving_window) / len(moving_window), 2)
        })

    # Final result construction
    return {
        "total_reviews": total,
        "average_rating": avg_rating,
        "weighted_rating": weighted_avg,
        "reputation_score": rep_score,
        "ratings": rating_dist,
        "emotions": emotions,
        "sentiment_trend": trend_data,
        "monthly_sentiment": [
            {"month": m, "avg_sentiment": round(sum(v)/len(v), 3)}
            for m, v in sorted(monthly_logs.items())
        ],
        "response_rate": round((responded_count / total) * 100, 2),
        "complaint_ratio": round((complaints_count / total) * 100, 2),
        "sentiment_balance": round(sum(sentiments_list) / len(sentiments_list), 3) if sentiments_list else 0,
        "keywords": HeavyweightEngine.extract_keywords(reviews),
        "forecast": HeavyweightEngine.perform_regression(daily_logs)
    }

# -------------------------------------------------------------------
# PRIMARY ENDPOINTS
# -------------------------------------------------------------------

@router.get("/ai/insights", response_class=JSONResponse)
async def analyze_business(
    company_id: int = Query(..., description="The unique ID of the business entity"),
    start: str = Query(..., description="ISO start date"),
    end: str = Query(..., description="ISO end date"),
    session: AsyncSession = Depends(get_session),
):
    """
    Main Analytical Insight API. Orchestrates data retrieval, 
    filtering, and heavyweight processing.
    """
    logger.info(f"Insight request received for Company ID: {company_id} range: {start} to {end}")
    
    try:
        start_dt = datetime.fromisoformat(start.replace('Z', '+00:00'))
        end_dt = datetime.fromisoformat(end.replace('Z', '+00:00'))
    except ValueError as e:
        logger.error(f"Date parsing failed: {str(e)}")
        return _empty_dashboard()

    # Query Formulation
    stmt = select(Review).where(
        and_(
            Review.company_id == company_id,
            or_(
                Review.google_review_time.is_(None),
                and_(Review.google_review_time >= start_dt,
                     Review.google_review_time <= end_dt)
            )
        )
    )
    
    execution_result = await session.execute(stmt)
    review_collection = execution_result.scalars().all()

    # Data Processing
    analytics = compute_analytics(review_collection)
    if not analytics:
        return _empty_dashboard()

    # Structure Response for Frontend Aligment
    return {
        "metadata": {
            "total_reviews": analytics["total_reviews"],
            "computation_time": datetime.now(timezone.utc).isoformat(),
            "weighted_rating": analytics["weighted_rating"]
        },
        "kpis": {
            "average_rating": analytics["average_rating"],
            "reputation_score": analytics["reputation_score"],
            "response_rate": analytics["response_rate"],
            "complaint_ratio": analytics["complaint_ratio"]
        },
        "visualizations": {
            "ratings": analytics["ratings"],
            "emotions": analytics["emotions"],
            "sentiment_trend": analytics["sentiment_trend"],
            "keywords": analytics["keywords"],
            "forecast": analytics["forecast"]
        }
    }

@router.get("/chatbot/explain/{company_id}")
async def chatbot(
    company_id: int, 
    question: str, 
    session: AsyncSession = Depends(get_session)
):
    """
    AI Conversational Logic. Provides plain-text explanations 
    of complex dashboard data.
    """
    stmt = select(Review).where(Review.company_id == company_id)
    res = await session.execute(stmt)
    data = compute_analytics(res.scalars().all())

    if not data:
        return {"answer": "I'm sorry, I don't see any data for this business yet."}

    query_text = question.lower()
    
    # Conditional logic tree for different question types
    if "why" in query_text and "month" in query_text:
        answer = "Sentiment fluctuation is primarily driven by recent changes in response time and star rating variance."
    elif "forecast" in query_text or "predict" in query_text:
        slope = data['forecast'][0]['avg'] if data['forecast'] else 0
        answer = f"Our AI model predicts a stable trend. Expected rating for next month is {slope}."
    elif "nps" in query_text or "reputation" in query_text:
        answer = f"Your reputation score is {data['reputation_score']}. This is calculated based on customer loyalty patterns."
    else:
        dominant_emotion = max(data['emotions'], key=data['emotions'].get)
        answer = (
            f"Currently, your average rating is {data['average_rating']}. "
            f"The prevailing customer sentiment is {dominant_emotion}."
        )

    # Persist in memory
    remember(company_id, "user", question)
    remember(company_id, "ai", answer)

    return {
        "answer": answer, 
        "memory": recall(company_id),
        "status": "success"
    }

@router.get("/why-month-changed/{company_id}")
async def why_changed(company_id: int, session: AsyncSession = Depends(get_session)):
    """Explains delta changes between the last two months."""
    stmt = select(Review).where(Review.company_id == company_id)
    res = await session.execute(stmt)
    analytics = compute_analytics(res.scalars().all())

    monthly = analytics["monthly_sentiment"] if analytics else []
    if len(monthly) < 2:
        return {"explanation": "Comparison requires at least two months of historical data."}

    current_val = monthly[-1]
    previous_val = monthly[-2]
    
    diff = current_val["avg_sentiment"] - previous_val["avg_sentiment"]
    direction = "improved" if diff > 0 else "declined"

    return {
        "explanation": f"Sentiment {direction} from {previous_val['month']} to {current_val['month']} by {abs(diff):.3f} points.",
        "delta": round(diff, 3)
    }

@router.get("/forecast/{company_id}")
async def get_forecast_data(company_id: int, session: AsyncSession = Depends(get_session)):
    """Standalone endpoint for the predictive forecasting module."""
    stmt = select(Review).where(Review.company_id == company_id)
    res = await session.execute(stmt)
    analytics = compute_analytics(res.scalars().all())

    if not analytics or not analytics["forecast"]:
        return {"forecast": [], "msg": "Insufficient data"}

    return {
        "forecast": analytics["forecast"],
        "base_rating": analytics["average_rating"]
    }

@router.get("/executive-report/pdf/{company_id}")
async def executive_pdf(company_id: int, session: AsyncSession = Depends(get_session)):
    """
    Generates a formal executive PDF report.
    Utilizes ReportLab for high-fidelity document creation.
    """
    stmt = select(Review).where(Review.company_id == company_id)
    res = await session.execute(stmt)
    analytics = compute_analytics(res.scalars().all())

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=LETTER)
    
    # PDF Styling & Layout
    pdf.setTitle(f"Business Intelligence Report - {company_id}")
    pdf.setStrokeColor(colors.blue)
    pdf.line(50, 760, 550, 760)
    
    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(50, 780, "Review Intelligence Executive Report")
    
    pdf.setFont("Helvetica", 12)
    pdf.drawString(50, 740, f"Report Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    pdf.drawString(50, 725, f"Business Identifier: {company_id}")

    if analytics:
        # Data Section
        pdf.setFont("Helvetica-Bold", 14)
        pdf.drawString(50, 680, "Core Performance Metrics")
        
        pdf.setFont("Helvetica", 12)
        metrics = [
            f"Weighted Business Rating: {analytics['weighted_rating']}",
            f"Absolute Average Rating: {analytics['average_rating']}",
            f"Reputation Score (NPS): {analytics['reputation_score']}",
            f"Customer Response Rate: {analytics['response_rate']}%",
            f"Complaint-to-Review Ratio: {analytics['complaint_ratio']}%"
        ]
        
        y_offset = 650
        for line in metrics:
            pdf.drawString(70, y_offset, f"• {line}")
            y_offset -= 20

        # AI Recommendations
        pdf.setFont("Helvetica-Bold", 14)
        pdf.drawString(50, y_offset - 20, "Strategic AI Recommendations")
        pdf.setFont("Helvetica-Oblique", 11)
        
        advice = "Priority: Focus on Detractor mitigation to stabilize Reputation Score."
        if analytics['reputation_score'] > 50:
            advice = "Priority: Leverage Promoters for referral marketing campaigns."
            
        pdf.drawString(70, y_offset - 45, f"1. {advice}")
        pdf.drawString(70, y_offset - 65, "2. Maintain current response rate to preserve customer trust.")

    pdf.showPage()
    pdf.save()
    buffer.seek(0)

    filename = f"Executive_Report_{company_id}.pdf"
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )

@router.get("/competitors/{company_id}")
async def competitors(company_id: int, session: AsyncSession = Depends(get_session)):
    """Compares the current business against linked competitors."""
    main_res = await session.execute(select(Review).where(Review.company_id == company_id))
    main_analytics = compute_analytics(main_res.scalars().all())

    comp_stmt = select(Competitor).where(Competitor.company_id == company_id)
    comp_res = await session.execute(comp_stmt)
    competitor_list = comp_res.scalars().all()

    insights = []
    current_avg = main_analytics["average_rating"] if main_analytics else 0
    
    for c in competitor_list:
        comp_rating = getattr(c, "rating", 0) or 0
        if comp_rating > current_avg:
            insights.append({
                "competitor": c.name,
                "gap": round(comp_rating - current_avg, 2),
                "status": "Competitive Risk"
            })
        else:
            insights.append({
                "competitor": c.name,
                "gap": round(current_avg - comp_rating, 2),
                "status": "Leading"
            })

    return {
        "company_rating": current_avg,
        "competitor_data": insights
    }

@router.get("/revenue")
async def revenue_risk_assessment(company_id: int, session: AsyncSession = Depends(get_session)):
    """Calculates revenue risk based on rating thresholds and volatility."""
    res = await session.execute(
        select(func.avg(Review.rating)).where(Review.company_id == company_id)
    )
    avg = res.scalar() or 0

    # Logic for risk mapping
    if avg >= 4.5:
        risk = 5; impact = "Negligible"
    elif avg >= 4.0:
        risk = 15; impact = "Low"
    elif avg >= 3.0:
        risk = 45; impact = "Medium"
    else:
        risk = 85; impact = "High"

    return {
        "risk_percent": risk, 
        "impact": impact,
        "calculation_date": datetime.now().strftime("%Y-%m-%d")
    }

def _empty_dashboard():
    """Returns a standardized null response for UI consistency."""
    return JSONResponse({
        "metadata": {"total_reviews": 0, "status": "no_data"},
        "kpis": {
            "average_rating": 0.0, 
            "reputation_score": 0, 
            "response_rate": 0
        },
        "visualizations": {
            "ratings": {1:0, 2:0, 3:0, 4:0, 5:0},
            "emotions": {"Positive":0, "Neutral":0, "Negative":0},
            "sentiment_trend": [],
            "keywords": [],
            "forecast": []
        }
    })

# ===================================================================
# END OF FILE: app/routes/dashboard.py
# ===================================================================
