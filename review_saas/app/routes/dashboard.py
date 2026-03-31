import logging
from datetime import date, datetime, timedelta
from typing import Optional, Dict, List
from collections import Counter, defaultdict

import numpy as np
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from starlette.templating import Jinja2Templates
from sklearn.linear_model import LinearRegression

from app.core.db import get_session
# REMOVED ChatMessage from imports to prevent ImportError
from app.core.models import Review, Company 

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])
logger = logging.getLogger("app.routes.dashboard")
templates = Jinja2Templates(directory="app/templates")


# ======================================================
# DASHBOARD PAGE (SERVE FRONTEND)
# ======================================================
@router.get("/", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    """
    Serve the dashboard HTML page
    """
    return templates.TemplateResponse(request=request, name="dashboard.html", context={})


# ======================================================
# DASHBOARD MAIN DATA API
# ======================================================
@router.get("/ai/insights")
async def dashboard_data(
    company_id: int = Query(...),
    start: Optional[date] = Query(None),
    end: Optional[date] = Query(None),
    session: AsyncSession = Depends(get_session),
):
    """
    Returns all KPI & visualization data for frontend charts
    """
    # Default date range
    if not start:
        start = date.today() - timedelta(days=365) # Checking more history
    if not end:
        end = date.today()

    stmt = select(Review).where(
        Review.company_id == company_id,
        Review.date >= start,
        Review.date <= end
    )

    result = await session.execute(stmt)
    reviews = result.scalars().all()

    if not reviews:
        return {
            "metadata": {"company_id": company_id, "total_reviews": 0},
            "kpis": {
                "average_rating": "0.0",
                "reputation_score": "0/100"
            },
            "visualizations": {
                "emotions": {"Positive": 0, "Neutral": 0, "Negative": 0},
                "sentiment_trend": [],
                "ratings": {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0}
            }
        }

    # ==================================================
    # AGGREGATE KPIs
    # ==================================================
    total_reviews = len(reviews)
    avg_rating = round(sum(r.rating for r in reviews) / total_reviews, 1)

    # Reputation score: scale to 0-100 based on sentiment
    valid_sentiments = [r.sentiment_score for r in reviews if r.sentiment_score is not None]
    avg_sent = sum(valid_sentiments) / len(valid_sentiments) if valid_sentiments else 0
    reputation_score = f"{int(((avg_sent + 1) / 2) * 100)}/100"

    # ==================================================
    # RATING DISTRIBUTION
    # ==================================================
    rating_dist = {str(i): 0 for i in range(1, 6)}
    for r in reviews:
        key = str(int(r.rating))
        if key in rating_dist:
            rating_dist[key] += 1

    # ==================================================
    # EMOTIONS RADAR (Matches Radar Labels in HTML)
    # ==================================================
    emotions_radar = {
        "Trust": 80 if avg_rating >= 4 else 40,
        "Joy": 70 if avg_sent > 0.2 else 20,
        "Surprise": 50,
        "Sadness": 40 if avg_sent < 0 else 10,
        "Fear": 30 if avg_sent < -0.2 else 5,
        "Anger": 60 if avg_sent < -0.5 else 5
    }

    # ==================================================
    # SENTIMENT TREND (for line chart)
    # ==================================================
    trend_map = defaultdict(list)
    for r in reviews:
        trend_map[r.date.isoformat()].append(r.sentiment_score or 0)

    sentiment_trend = [
        {"week": d, "avg": round(sum(vals) / len(vals), 2)}
        for d, vals in sorted(trend_map.items())
    ]

    return {
        "metadata": {"company_id": company_id, "total_reviews": total_reviews},
        "kpis": {
            "average_rating": avg_rating,
            "reputation_score": reputation_score
        },
        "visualizations": {
            "emotions": emotions_radar,
            "sentiment_trend": sentiment_trend[-20:],
            "ratings": rating_dist
        }
    }


# ======================================================
# REVENUE RISK (Populates the Red Card)
# ======================================================
@router.get("/revenue")
async def revenue_risk(company_id: int = Query(...), session: AsyncSession = Depends(get_session)):
    stmt = select(Review).where(Review.company_id == company_id)
    result = await session.execute(stmt)
    reviews = result.scalars().all()

    if not reviews:
        return {"risk_percent": 0, "impact": "N/A"}

    bad_count = sum(1 for r in reviews if r.rating <= 2)
    risk_percent = int((bad_count / len(reviews)) * 100)
    
    impact = "LOW"
    if risk_percent > 15: impact = "MEDIUM"
    if risk_percent > 35: impact = "CRITICAL"

    return {"risk_percent": risk_percent, "impact": impact}


# ======================================================
# COMPANY LIST
# ======================================================
@router.get("/companies")
async def list_companies(session: AsyncSession = Depends(get_session)):
    stmt = select(Company)
    result = await session.execute(stmt)
    companies = result.scalars().all()
    return {"companies": [{"id": c.id, "name": c.name} for c in companies]}


# ======================================================
# CHATBOT INTEGRATION (REMOVED DB STORAGE TO PREVENT CRASH)
# ======================================================
@router.post("/chatbot/chat")
async def chat_ai(request: Request):
    """
    Simulated AI response without DB storage for ChatMessage
    """
    data = await request.json()
    message = data.get("message", "")
    
    # Simulated AI response
    answer = f"Based on your reviews, I suggest focusing on response time. (Simulated for: {message[:20]}...)"
    
    return {"answer": answer}

# ======================================================
# REVIEW SYNC
# ======================================================
@router.post("/reviews/ingest/{company_id}")
async def sync_reviews(company_id: int, session: AsyncSession = Depends(get_session)):
    """
    Pull latest reviews simulation
    """
    return {"reviews_count": 0, "status": "Ready for live sync"}
