# filename: app/routes/dashboard.py
# ✅ Clean backend data provider for Dashboard
# ✅ Analytics & charts handled on FRONTEND

import logging
from datetime import datetime
from typing import Optional, Dict, Any

from fastapi import APIRouter, Depends, Query, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from starlette.templating import Jinja2Templates

from app.core.db import get_session
from app.core.models import Review

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
logger = logging.getLogger("app.routes.dashboard")

templates = Jinja2Templates(directory="app/templates")

# ======================================================
# HELPER — DATE PARSER (SAFE)
# ======================================================

def parse_date(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


# ======================================================
# 1️⃣ DASHBOARD PAGE (HTML)
# ======================================================

@router.get("/", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
        }
    )


# ======================================================
# 2️⃣ CORE DATA API — USED BY "Analyze Business"
# ======================================================

@router.get("/ai/insights")
async def dashboard_data(
    company_id: int = Query(...),
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_session),
):
    """
    Returns RAW, FRONTEND‑READY data.
    Frontend (Chart.js) performs the visualization & analysis.
    """

    start_dt = parse_date(start)
    end_dt = parse_date(end)

    stmt = select(Review).where(Review.company_id == company_id)

    if start_dt:
        stmt = stmt.where(Review.created_at >= start_dt)
    if end_dt:
        stmt = stmt.where(Review.created_at <= end_dt)

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
    # BASIC AGGREGATES (NO AI / NO NLP here)
    # ======================================================

    total_reviews = len(reviews)
    avg_rating = round(sum(r.rating for r in reviews) / total_reviews, 1)

    rating_dist = {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0}
    trend_map: Dict[str, list] = {}

    positive = neutral = negative = 0

    for r in reviews:
        rating_key = str(int(r.rating))
        if rating_key in rating_dist:
            rating_dist[rating_key] += 1

        # Sentiment score assumed stored in DB (-1 to +1)
        score = r.sentiment_score or 0

        if score >= 0.2:
            positive += 1
        elif score <= -0.2:
            negative += 1
        else:
            neutral += 1

        # Trend grouped by DATE
        d = r.created_at.date().isoformat()
        trend_map.setdefault(d, []).append(r.rating)

    sentiment_trend = [
        {
            "week": date,
            "avg": round(sum(vals) / len(vals), 2)
        }
        for date, vals in sorted(trend_map.items())
    ]

    emotions = {
        "Positive": positive,
        "Neutral": neutral,
        "Negative": negative
    }

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
            "emotions": emotions,
            "sentiment_trend": sentiment_trend,
            "ratings": rating_dist
        }
    })


# ======================================================
# 3️⃣ REVENUE RISK (SIMPLE FRONTEND‑READY METRIC)
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

    bad_reviews = sum(1 for r in reviews if r.rating <= 2)
    risk = int((bad_reviews / len(reviews)) * 100)

    impact = "Low"
    if risk > 15:
        impact = "Medium"
    if risk > 35:
        impact = "High"

    return {
        "risk_percent": risk,
        "impact": impact
    }
