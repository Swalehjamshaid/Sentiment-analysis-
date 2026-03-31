# filename: app/routes/dashboard.py
# =========================================================
# Review Intelligence Dashboard (Backend)
# Fully aligned with:
# - app/core/db.py
# - app/core/models.py
# - dashboard.html (frontend JS)
# =========================================================

from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime
from collections import defaultdict
from starlette.templating import Jinja2Templates

from app.core.db import get_session
from app.core.models import Review

# Router prefix MUST match frontend fetches
router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

templates = Jinja2Templates(directory="app/templates")


# =========================================================
# DASHBOARD PAGE (HTML)
# =========================================================

@router.get("/", response_class=HTMLResponse)
async def dashboard_page(request):
    """
    Serves dashboard.html.
    Frontend handles all interactions.
    """
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request}
    )


# =========================================================
# ANALYZE BUSINESS (MAIN DATA ENDPOINT)
# =========================================================

@router.get("/ai/insights")
async def analyze_business(
    company_id: int = Query(...),
    start: str = Query(...),
    end: str = Query(...),
    session: AsyncSession = Depends(get_session),
):
    """
    Provides ALL data required by dashboard.html charts & KPIs.
    The frontend handles visualization; backend aggregates data.
    """

    # -----------------------------------------------------
    # Parse dates safely (frontend sends YYYY-MM-DD)
    # -----------------------------------------------------
    try:
        start_dt = datetime.fromisoformat(start)
        end_dt = datetime.fromisoformat(end)
    except Exception:
        return _empty_response()

    # -----------------------------------------------------
    # Fetch reviews from PostgreSQL
    # IMPORTANT: Uses google_review_time (REAL column)
    # -----------------------------------------------------
    stmt = select(Review).where(
        Review.company_id == company_id,
        Review.google_review_time >= start_dt,
        Review.google_review_time <= end_dt
    )

    result = await session.execute(stmt)
    reviews = result.scalars().all()
    total_reviews = len(reviews)

    if total_reviews == 0:
        return _empty_response()

    # -----------------------------------------------------
    # KPI Calculations
    # -----------------------------------------------------
    avg_rating = round(
        sum((r.rating or 0) for r in reviews) / total_reviews,
        2
    )

    reputation_score = int((avg_rating / 5) * 100)

    # -----------------------------------------------------
    # Rating Distribution (BAR CHART)
    # -----------------------------------------------------
    ratings = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    for r in reviews:
        if r.rating in ratings:
            ratings[r.rating] += 1

    # -----------------------------------------------------
    # Emotion Radar (RADAR CHART)
    # Uses stored sentiment_score
    # -----------------------------------------------------
    emotions = {"Positive": 0, "Neutral": 0, "Negative": 0}
    for r in reviews:
        score = r.sentiment_score or 0
        if score >= 0.25:
            emotions["Positive"] += 1
        elif score <= -0.25:
            emotions["Negative"] += 1
        else:
            emotions["Neutral"] += 1

    # -----------------------------------------------------
    # Sentiment Trend (LINE CHART)
    # Grouped by day
    # -----------------------------------------------------
    trend_map = defaultdict(list)
    for r in reviews:
        day = r.google_review_time.strftime("%Y-%m-%d")
        trend_map[day].append(r.rating or 0)

    sentiment_trend = [
        {
            "week": day,
            "avg": round(sum(vals) / len(vals), 2)
        }
        for day, vals in sorted(trend_map.items())
    ]

    # -----------------------------------------------------
    # FINAL RESPONSE (MATCHES FRONTEND)
    # -----------------------------------------------------
    return {
        "metadata": {
            "total_reviews": total_reviews
        },
        "kpis": {
            "average_rating": avg_rating,
            "reputation_score": reputation_score
        },
        "visualizations": {
            "ratings": ratings,
            "emotions": emotions,
            "sentiment_trend": sentiment_trend
        }
    }


# =========================================================
# REVENUE RISK MONITORING
# =========================================================

@router.get("/revenue")
async def revenue_risk(
    company_id: int = Query(...),
    session: AsyncSession = Depends(get_session),
):
    """
    Simple revenue risk scoring based on average rating.
    Used by dashboard.html.
    """

    stmt = select(func.avg(Review.rating)).where(
        Review.company_id == company_id
    )
    result = await session.execute(stmt)
    avg_rating = result.scalar() or 0

    if avg_rating >= 4:
        return {"risk_percent": 10, "impact": "Low"}
    elif avg_rating >= 3:
        return {"risk_percent": 40, "impact": "Medium"}
    else:
        return {"risk_percent": 80, "impact": "High"}


# =========================================================
# HELPERS
# =========================================================

def _empty_response():
    """
    Returns frontend-safe empty payload
    """
    return JSONResponse({
        "metadata": {
            "total_reviews": 0
        },
        "kpis": {
            "average_rating": 0,
            "reputation_score": 0
        },
        "visualizations": {
            "ratings": {1:0, 2:0, 3:0, 4:0, 5:0},
            "emotions": {"Positive":0, "Neutral":0, "Negative":0},
            "sentiment_trend": []
        }
    })
