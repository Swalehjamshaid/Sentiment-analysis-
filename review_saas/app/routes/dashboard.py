from __future__ import annotations
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime, timezone
from collections import defaultdict
from typing import Dict, Any

# Core imports
from app.core.db import get_session
from app.core.models import Review, Company

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])

# ---------------------------------------------------------
# MAIN AI DASHBOARD ENDPOINT
# ---------------------------------------------------------
@router.get("/ai/insights")
async def get_dashboard_insights(
    company_id: int = Query(...),
    start: str = Query(...),
    end: str = Query(...),
    db: AsyncSession = Depends(get_session)
):
    """
    Returns aggregated insights, KPIs, and visualization data 
    aligned with the ReviewSaaS frontend requirements.
    """
    try:
        # 1. Parse dates safely from ISO format
        try:
            start_date = datetime.fromisoformat(start.replace('Z', '+00:00'))
            end_date = datetime.fromisoformat(end.replace('Z', '+00:00'))
        except (ValueError, TypeError):
            # Fallback to a wider range if parsing fails
            start_date = datetime(2024, 1, 1, tzinfo=timezone.utc)
            end_date = datetime.now(timezone.utc)

        # 2. Fetch reviews within the date range and company
        stmt = select(Review).where(
            Review.company_id == company_id,
            Review.first_seen_at >= start_date,
            Review.first_seen_at <= end_date
        )
        result = await db.execute(stmt)
        reviews = result.scalars().all()
        
        total_reviews = len(reviews)

        # 3. KPI Calculations
        avg_rating = 0.0
        reputation_score = 0.0
        
        if total_reviews > 0:
            avg_rating = sum((r.rating or 0) for r in reviews) / total_reviews
            # sentiment_score is usually -1 to 1; we provide an average for the dashboard
            reputation_score = sum((r.sentiment_score or 0) for r in reviews) / total_reviews

        # 4. Rating Distribution (Bar Chart)
        ratings_dist = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        for r in reviews:
            if r.rating and 1 <= r.rating <= 5:
                ratings_dist[r.rating] += 1

        # 5. Sentiment Trend (Line Chart) - Grouped by Month
        trend_map = defaultdict(list)
        for r in reviews:
            if r.first_seen_at:
                month_key = r.first_seen_at.strftime("%Y-%m")
                trend_map[month_key].append(r.sentiment_score or 0)

        sentiment_trend = []
        for month in sorted(trend_map.keys()):
            scores = trend_map[month]
            sentiment_trend.append({
                "month": month,
                "avg": round(sum(scores) / len(scores), 2)
            })

        # 6. Emotion Radar (Radar Chart)
        # Logic: Categorizing sentiment_score into buckets
        emotions = {"happy": 0, "neutral": 0, "angry": 0}
        for r in reviews:
            score = r.sentiment_score or 0
            if score > 0.3:
                emotions["happy"] += 1
            elif score < -0.3:
                emotions["angry"] += 1
            else:
                emotions["neutral"] += 1

        # 7. Final Response Construction
        return {
            "metadata": {
                "total_reviews": total_reviews,
                "queried_at": datetime.now(timezone.utc).isoformat()
            },
            "kpis": {
                "average_rating": round(avg_rating, 2),
                "reputation_score": round(reputation_score, 2)
            },
            "visualizations": {
                "ratings": ratings_dist,
                "sentiment_trend": sentiment_trend,
                "emotions": emotions
            }
        }

    except Exception as e:
        return {
            "metadata": {"total_reviews": 0},
            "kpis": {"average_rating": 0, "reputation_score": 0},
            "visualizations": {
                "ratings": {1: 0, 2: 0, 3: 0, 4: 0, 5: 0},
                "sentiment_trend": [],
                "emotions": {"happy": 0, "neutral": 0, "angry": 0}
            },
            "error": str(e)
        }

# ---------------------------------------------------------
# REVENUE RISK ENDPOINT
# ---------------------------------------------------------
@router.get("/revenue")
async def get_revenue_risk(
    company_id: int,
    db: AsyncSession = Depends(get_session)
):
    """
    Calculates business risk based on the average rating.
    """
    try:
        result = await db.execute(
            select(func.avg(Review.rating)).where(Review.company_id == company_id)
        )
        avg_rating = result.scalar() or 0.0

        # Logic for Revenue Risk
        if avg_rating >= 4.0:
            risk_percent = 10
            impact = "Low"
        elif avg_rating >= 3.0:
            risk_percent = 45
            impact = "Medium"
        else:
            risk_percent = 85
            impact = "High"

        return {
            "risk_percent": risk_percent,
            "impact": impact,
            "based_on_rating": round(avg_rating, 2)
        }
    except Exception as e:
        return {
            "risk_percent": 0,
            "impact": "N/A",
            "error": str(e)
        }
