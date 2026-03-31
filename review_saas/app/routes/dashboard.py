import logging
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.core.db import get_session
from app.core.models import Review, Company

router = APIRouter()
logger = logging.getLogger("app.routes.dashboard")

@router.get("/ai/insights")
async def get_ai_insights(
    company_id: int,
    start: Optional[date] = Query(None),
    end: Optional[date] = Query(None),
    db: AsyncSession = Depends(get_session)
):
    """
    Core data provider for the 'Analyze Business' button.
    Fetches data from Postgres and formats it for Radar, Line, and Bar charts.
    """
    try:
        # 1. Fetch Reviews for the selected Company and Date Range
        stmt = select(Review).where(Review.company_id == company_id)
        if start:
            stmt = stmt.where(Review.date >= start)
        if end:
            stmt = stmt.where(Review.date <= end)
        else:
            # Default to today if no end date provided
            end = date.today()
            
        result = await db.execute(stmt)
        reviews = result.scalars().all()

        # Handle Empty State (If no records found for this specific company_id)
        if not reviews:
            return {
                "metadata": {"total_reviews": 0},
                "kpis": {"average_rating": "—", "reputation_score": "—"},
                "visualizations": {
                    "emotions": {"Trust": 0, "Joy": 0, "Surprise": 0, "Sadness": 0, "Fear": 0, "Anger": 0},
                    "sentiment_trend": [],
                    "ratings": {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0}
                }
            }

        # 2. KPI Calculations
        total_count = len(reviews)
        avg_rating = round(sum(r.rating for r in reviews) / total_count, 1)
        
        # Calculate Reputation Score (Normalizing sentiment -1 to 1 into 0-100)
        valid_sentiments = [r.sentiment_score for r in reviews if r.sentiment_score is not None]
        avg_sent = sum(valid_sentiments) / len(valid_sentiments) if valid_sentiments else 0
        reputation_score_val = int(((avg_sent + 1) / 2) * 100)

        # 3. Rating Distribution (For 'chartRatings' bar chart)
        rating_counts = {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0}
        for r in reviews:
            r_key = str(int(r.rating))
            if r_key in rating_counts:
                rating_counts[r_key] += 1

        # 4. Sentiment Trend (For 'chartMonthly' line chart)
        # Group reviews by date to show progress over time
        trend_data = {}
        for r in reviews:
            d_str = r.date.strftime("%Y-%m-%d")
            if d_str not in trend_data:
                trend_data[d_str] = []
            trend_data[d_str].append(r.sentiment_score or 0)
        
        # Format for Chart.js (labels must match keys in JS)
        sorted_dates = sorted(trend_data.keys())
        sentiment_trend = [
            {"week": d, "avg": round(sum(scores)/len(scores), 2)} 
            for d in sorted_dates
        ]

        # 5. Emotion Radar (Calculated Intensity)
        # This provides the 'CUSTOMER EMOTION RADAR' data
        emotions = {
            "Trust": 80 if avg_sent > 0.4 else 45,
            "Joy": 75 if avg_sent > 0.2 else 30,
            "Surprise": 50,
            "Sadness": 35 if avg_sent < 0 else 10,
            "Fear": 25 if avg_sent < -0.1 else 5,
            "Anger": 55 if avg_sent < -0.4 else 5
        }

        return {
            "metadata": {"total_reviews": total_count},
            "kpis": {
                "average_rating": avg_rating,
                "reputation_score": f"{reputation_score_val}/100"
            },
            "visualizations": {
                "emotions": emotions,
                "sentiment_trend": sentiment_trend[-15:], # Last 15 data points
                "ratings": rating_counts
            }
        }
    except Exception as e:
        logger.error(f"❌ Dashboard Insights Error: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error in Dashboard Insights")

@router.get("/revenue")
async def get_revenue_risk(
    company_id: int,
    db: AsyncSession = Depends(get_session)
):
    """
    Populates the 'Revenue Risk Monitoring' (Red Card).
    Calculates probability of loss based on recent review spikes.
    """
    try:
        # Look at the most recent 20 reviews
        stmt = select(Review).where(Review.company_id == company_id).order_by(Review.date.desc()).limit(20)
        result = await db.execute(stmt)
        recent = result.scalars().all()
        
        if not recent:
            return {"risk_percent": 0, "impact": "N/A"}

        # Calculate percentage of negative reviews (Rating 1 or 2)
        neg_reviews = [r for r in recent if r.rating <= 2]
        risk_percent = int((len(neg_reviews) / len(recent)) * 100)
        
        # Determine Impact Level text
        impact = "STABLE"
        if risk_percent > 15: impact = "MODERATE"
        if risk_percent > 40: impact = "CRITICAL"

        return {
            "risk_percent": risk_percent,
            "impact": impact
        }
    except Exception as e:
        logger.error(f"❌ Revenue Risk Error: {e}")
        return {"risk_percent": 0, "impact": "ERROR"}
