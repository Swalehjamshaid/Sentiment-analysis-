import logging
import os
from datetime import date, datetime, timedelta
from typing import Optional, Dict, List
from collections import Counter, defaultdict

import numpy as np
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from starlette.templating import Jinja2Templates

from app.core.db import get_session
from app.core.models import Review, Company 

# Router defined WITHOUT internal prefix to match main.py mounting
router = APIRouter(tags=["dashboard"])
logger = logging.getLogger("app.routes.dashboard")
templates = Jinja2Templates(directory="app/templates")

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
    Core engine for the 'Analyze Business' button.
    Fetches ALL historical data for the given company ID.
    """
    try:
        # 1. Fetching ALL reviews (Removed all limits)
        stmt = select(Review).where(Review.company_id == company_id)
        
        # Applying date filters if they exist
        if start:
            stmt = stmt.where(Review.date >= start)
        if end:
            stmt = stmt.where(Review.date <= end)

        result = await session.execute(stmt)
        reviews = result.scalars().all()

        # Handle 0 result case
        if not reviews:
            logger.warning(f"⚠️ No reviews found for Company ID: {company_id} in Postgres.")
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
        
        valid_sentiments = [r.sentiment_score for r in reviews if r.sentiment_score is not None]
        avg_sent = sum(valid_sentiments) / len(valid_sentiments) if valid_sentiments else 0
        rep_score = f"{int(((avg_sent + 1) / 2) * 100)}/100"

        # 3. Distributions for Charts
        rating_dist = {str(i): 0 for i in range(1, 6)}
        trend_map = defaultdict(list)
        
        for r in reviews:
            # Bar Chart Data
            r_key = str(int(round(r.rating)))
            if r_key in rating_dist:
                rating_dist[r_key] += 1
            
            # Line Chart Data
            trend_map[r.date.isoformat()].append(r.sentiment_score or 0)

        # 4. Final Formatting for Chart.js
        sentiment_trend = [
            {"week": d, "avg": round(sum(vals) / len(vals), 2)}
            for d, vals in sorted(trend_map.items())
        ]

        emotions_radar = {
            "Trust": 80 if avg_rating >= 4 else 45,
            "Joy": 75 if avg_sent > 0.2 else 25,
            "Surprise": 50,
            "Sadness": 40 if avg_sent < 0 else 10,
            "Fear": 30 if avg_sent < -0.2 else 5,
            "Anger": 60 if avg_sent < -0.4 else 5
        }

        return {
            "metadata": {"total_reviews": total_count},
            "kpis": {
                "average_rating": avg_rating,
                "reputation_score": rep_score
            },
            "visualizations": {
                "emotions": emotions_radar,
                "sentiment_trend": sentiment_trend,
                "ratings": rating_dist
            }
        }
    except Exception as e:
        logger.error(f"❌ Analysis Error: {e}")
        return {"error": str(e)}

# ======================================================
# REVENUE RISK (Red Card)
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
    
    impact = "STABLE"
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
    # Ensure keys match the 'companies' property expected by JavaScript
    return {"companies": [{"id": c.id, "name": c.name} for c in companies]}

# ======================================================
# CHATBOT & SYNC (Placeholders to prevent frontend errors)
# ======================================================
@router.post("/chatbot/chat")
async def chat_ai(request: Request):
    return {"answer": "AI Analysis ready. Please ask a question about your reviews."}

@router.post("/reviews/ingest/{company_id}")
async def sync_reviews(company_id: int):
    return {"reviews_count": 0, "status": "Database loaded"}
