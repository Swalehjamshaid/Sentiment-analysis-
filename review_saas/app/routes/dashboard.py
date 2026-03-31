# filename: app/routes/dashboard.py
# ==========================================================
# REVIEW INTELLIGENCE DASHBOARD – ENTERPRISE GRADE
#
# ✅ Frontend input/output UNCHANGED
# ✅ PostgreSQL optimized
# ✅ Null-safe, defensive, scalable
# ✅ Analytics-ready (hidden metrics)
# ==========================================================

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from datetime import datetime
from collections import defaultdict

from app.core.db import get_session
from app.core.models import Review

# DO NOT MODIFY — main.py mounts with prefix="/api"
router = APIRouter(prefix="/dashboard", tags=["dashboard"])


# ==========================================================
# MAIN DASHBOARD ENDPOINT
# ==========================================================
@router.get("/ai/insights")
async def analyze_business(
    company_id: int = Query(...),
    start: str = Query(...),
    end: str = Query(...),
    session: AsyncSession = Depends(get_session),
):
    """
    Comprehensive dashboard data provider.

    ⚠️ CONTRACT GUARANTEE:
    - Input unchanged
    - Output unchanged
    - All enhancements are INTERNAL only
    """

    # ------------------------------------------------------
    # 1. DATE NORMALIZATION (DEFENSIVE)
    # ------------------------------------------------------
    try:
        start_dt = datetime.fromisoformat(start)
        end_dt = datetime.fromisoformat(end)
    except Exception:
        return _empty_dashboard_response()

    # ------------------------------------------------------
    # 2. SINGLE, OPTIMIZED DATABASE QUERY
    # ------------------------------------------------------
    stmt = select(Review).where(
        and_(
            Review.company_id == company_id,
            or_(
                Review.google_review_time.is_(None),   # legacy reviews
                and_(
                    Review.google_review_time >= start_dt,
                    Review.google_review_time <= end_dt
                )
            )
        )
    )

    result = await session.execute(stmt)
    reviews = result.scalars().all()
    total_reviews = len(reviews)

    if total_reviews == 0:
        return _empty_dashboard_response()

    # ------------------------------------------------------
    # 3. INTERNAL DATA NORMALIZATION
    # ------------------------------------------------------
    ratings_clean = []
    sentiment_clean = []
    responded_count = 0
    complaint_count = 0
    praise_count = 0

    for r in reviews:
        if isinstance(r.rating, (int, float)):
            ratings_clean.append(r.rating)

        if isinstance(r.sentiment_score, (int, float)):
            sentiment_clean.append(r.sentiment_score)

        if r.review_reply_text:
            responded_count += 1

        if r.is_complaint:
            complaint_count += 1

        if r.is_praise:
            praise_count += 1

    # ------------------------------------------------------
    # 4. KPI CALCULATIONS (VISIBLE)
    # ------------------------------------------------------
    avg_rating = (
        round(sum(ratings_clean) / len(ratings_clean), 2)
        if ratings_clean else 0
    )

    reputation_score = int((avg_rating / 5) * 100) if avg_rating else 0

    # ------------------------------------------------------
    # 5. DISTRIBUTION & BUCKETING
    # ------------------------------------------------------
    rating_distribution = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    emotion_buckets = {"Positive": 0, "Neutral": 0, "Negative": 0}
    trend_map = defaultdict(list)

    for r in reviews:

        # Rating distribution
        if r.rating in rating_distribution:
            rating_distribution[r.rating] += 1

        # Sentiment distribution
        score = r.sentiment_score or 0
        if score >= 0.25:
            emotion_buckets["Positive"] += 1
        elif score <= -0.25:
            emotion_buckets["Negative"] += 1
        else:
            emotion_buckets["Neutral"] += 1

        # Trend aggregation
        if r.google_review_time:
            key = r.google_review_time.strftime("%Y-%m-%d")
            trend_map[key].append(r.rating or 0)

    sentiment_trend = [
        {
            "week": date,
            "avg": round(sum(vals) / len(vals), 2)
        }
        for date, vals in sorted(trend_map.items())
        if vals
    ]

    # ------------------------------------------------------
    # 6. HIDDEN ENHANCED ANALYTICS (NOT EXPOSED YET)
    # ------------------------------------------------------
    # These are intentionally calculated but not returned
    # so future versions can expose them without DB changes.

    _response_rate = (
        round((responded_count / total_reviews) * 100, 2)
        if total_reviews else 0
    )
    _complaint_ratio = (
        round((complaint_count / total_reviews) * 100, 2)
        if total_reviews else 0
    )
    _praise_ratio = (
        round((praise_count / total_reviews) * 100, 2)
        if total_reviews else 0
    )
    _sentiment_balance = (
        round(sum(sentiment_clean) / len(sentiment_clean), 3)
        if sentiment_clean else 0
    )

    # ------------------------------------------------------
    # 7. FINAL RESPONSE (STRICT CONTRACT)
    # ------------------------------------------------------
    return {
        "metadata": {
            "total_reviews": total_reviews
        },
        "kpis": {
            "average_rating": avg_rating,
            "reputation_score": reputation_score
        },
        "visualizations": {
            "ratings": rating_distribution,
            "emotions": emotion_buckets,
            "sentiment_trend": sentiment_trend
        }
    }


# ==========================================================
# REVENUE RISK MONITORING (UNCHANGED CONTRACT)
# ==========================================================
@router.get("/revenue")
async def revenue_risk(
    company_id: int = Query(...),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(func.avg(Review.rating))
        .where(Review.company_id == company_id)
    )

    avg_rating = result.scalar() or 0

    if avg_rating >= 4:
        return {"risk_percent": 10, "impact": "Low"}
    elif avg_rating >= 3:
        return {"risk_percent": 40, "impact": "Medium"}
    return {"risk_percent": 80, "impact": "High"}


# ==========================================================
# EMPTY STATE (FRONTEND‑SAFE)
# ==========================================================
def _empty_dashboard_response():
    return JSONResponse({
        "metadata": {"total_reviews": 0},
        "kpis": {
            "average_rating": 0,
            "reputation_score": 0
        },
        "visualizations": {
            "ratings": {1: 0, 2: 0, 3: 0, 4: 0, 5: 0},
            "emotions": {"Positive": 0, "Neutral": 0, "Negative": 0},
            "sentiment_trend": []
        }
    })
``
