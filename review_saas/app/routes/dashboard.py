# filename: app/routes/dashboard.py
# ✅ FIXED: Uses Review.date (NOT created_at)
# ✅ Frontend performs all analysis & charts

import logging
from datetime import datetime, date
from typing import Optional, Dict, Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from starlette.templating import Jinja2Templates

from app.core.db import get_session
from app.core.models import Review

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
logger = logging.getLogger("app.routes.dashboard")

templates = Jinja2Templates(directory="app/templates")


# ======================================================
# DASHBOARD PAGE
# ======================================================

@router.get("/", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request}
    )


# ======================================================
# CORE DATA API – Analyze Business
# ======================================================

@router.get("/ai/insights")
async def dashboard_data(
    company_id: int = Query(...),
    start: Optional[date] = Query(None),
    end: Optional[date] = Query(None),
    session: AsyncSession = Depends(get_session),
):
    """
    Fetch raw review data from Postgres.
    Frontend (Chart.js) handles ALL analysis & visualization.
    """

    stmt = select(Review).where(Review.company_id == company_id)

    # ✅ CORRECT column name
    if start:
        stmt = stmt.where(Review.date >= start)
    if end:
        stmt = stmt.where(Review.date <= end)

    result = await session.execute(stmt)
    reviews = result.scalars().all()

    # ---------------------------
    # EMPTY STATE
    # ---------------------------
    if not reviews:
        return JSONResponse({
            "metadata": {
                "company_id": company_id,
                "total_reviews": 0
            },
            "kpis": {
                "average_rating": 0,
                "reputation_score": 0
            },
            "visualizations": {
                "emotions": {
                    "Positive": 0,
                    "Neutral": 0,
                    "Negative": 0
                },
                "sentiment_trend": [],
                "ratings": {
                    "1": 0,
                    "2": 0,
                    "3": 0,
                    "4": 0,
                    "5": 0
                }
            }
        })

    # ======================================================
    # BASIC AGGREGATES (FRONTEND FRIENDLY)
    # ======================================================

    total_reviews = len(reviews)
    avg_rating = round(sum(r.rating for r in reviews) / total_reviews, 1)

    rating_dist = {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0}
    sentiment_counts = {"Positive": 0, "Neutral": 0, "Negative": 0}
    trend_map: Dict[str, list] = {}

    for r in reviews:
        # Rating distribution
        rating_key = str(int(r.rating))
        if rating_key in rating_dist:
            rating_dist[rating_key] += 1

        # Sentiment classification (using stored score)
        score = r.sentiment_score or 0
        if score >= 0.2:
            sentiment_counts["Positive"] += 1
        elif score <= -0.2:
            sentiment_counts["Negative"] += 1
        else:
            sentiment_counts["Neutral"] += 1

        # Trend grouping by DATE
        d = r.date.isoformat()
        trend_map.setdefault(d, []).append(r.rating)

    sentiment_trend = [
        {
            "week": d,
            "avg": round(sum(vals) / len(vals), 2)
        }
        for d, vals in sorted(trend_map.items())
    ]

    return JSONResponse({
        "metadata": {
            "company_id": company_id,
            "total_reviews": total_reviews
        },
        "kpis": {
            "average_rating": avg_rating,
            "reputation_score": round(avg_rating * 20, 0)
        },
        "visualizations": {
            "emotions": sentiment_counts,
            "sentiment_trend": sentiment_trend,
            "ratings": rating_dist
        }
    })


# ======================================================
# REVENUE RISK API (Used by dashboard)
# ======================================================

@router.get("/revenue")
async def revenue_risk(
    company_id: int = Query(...),
    session: AsyncSession = Depends(get_session),
):
    stmt = select(Review).where(Review.company_id == company_id)
    result = await session.execute(stmt)
    reviews = result.scalars().all()

    if not reviews:
        return {
            "risk_percent": 0,
            "impact": "N/A"
        }

    bad = sum(1 for r in reviews if r.rating <= 2)
    risk = int((bad / len(reviews)) * 100)

    impact = "Low"
    if risk > 15:
        impact = "Medium"
    if risk > 35:
        impact = "High"

    return {
        "risk_percent": risk,
        "impact": impact
    }
