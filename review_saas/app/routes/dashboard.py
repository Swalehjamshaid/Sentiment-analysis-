from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime
from collections import Counter, defaultdict

from app.core.db import get_session
from app.core.models import Review

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


# =========================================================
# 🔹 MAIN INSIGHTS API (USED BY FRONTEND)
# =========================================================
@router.get("/ai/insights")
async def get_dashboard_insights(
    company_id: int = Query(...),
    start: str = Query(None),
    end: str = Query(None),
    session: AsyncSession = Depends(get_session)
):
    try:
        # 🔹 Base Query
        query = select(Review).where(Review.company_id == company_id)

        # 🔹 Apply Date Filters
        if start:
            query = query.where(Review.created_at >= start)
        if end:
            query = query.where(Review.created_at <= end)

        result = await session.execute(query)
        reviews = result.scalars().all()

        # 🔥 DEBUG LOG
        print(f"📊 Reviews fetched for company {company_id}: {len(reviews)}")

        # =====================================================
        # ❌ IF NO DATA → RETURN SAFE STRUCTURE
        # =====================================================
        if not reviews:
            return {
                "metadata": {"total_reviews": 0},
                "kpis": {
                    "average_rating": 0,
                    "reputation_score": 0
                },
                "visualizations": {
                    "ratings": [0, 0, 0, 0, 0],
                    "emotions": {},
                    "sentiment_trend": [],
                    "keywords": []
                }
            }

        # =====================================================
        # ✅ KPI CALCULATIONS
        # =====================================================
        total_reviews = len(reviews)
        avg_rating = round(sum(r.rating for r in reviews) / total_reviews, 2)

        reputation_score = int((avg_rating / 5) * 100)

        # =====================================================
        # ✅ RATING DISTRIBUTION
        # =====================================================
        rating_counts = Counter(r.rating for r in reviews)

        ratings = [
            rating_counts.get(1, 0),
            rating_counts.get(2, 0),
            rating_counts.get(3, 0),
            rating_counts.get(4, 0),
            rating_counts.get(5, 0),
        ]

        # =====================================================
        # ✅ SENTIMENT TREND (BY WEEK)
        # =====================================================
        weekly = defaultdict(list)

        for r in reviews:
            if r.created_at:
                week = r.created_at.strftime("%Y-%U")
                weekly[week].append(r.rating)

        sentiment_trend = [
            {
                "week": k,
                "avg": round(sum(v) / len(v), 2)
            }
            for k, v in sorted(weekly.items())
        ]

        # =====================================================
        # ✅ SIMPLE KEYWORD EXTRACTION
        # =====================================================
        words = []
        for r in reviews:
            if r.review_text:
                words.extend(r.review_text.lower().split())

        common_words = Counter(words).most_common(15)

        keywords = [
            {"text": w, "value": c}
            for w, c in common_words
            if len(w) > 3
        ]

        # =====================================================
        # ✅ EMOTION (SIMPLIFIED MOCK)
        # =====================================================
        emotions = {
            "happy": sum(1 for r in reviews if r.rating >= 4),
            "neutral": sum(1 for r in reviews if r.rating == 3),
            "angry": sum(1 for r in reviews if r.rating <= 2),
        }

        # =====================================================
        # ✅ FINAL RESPONSE (MATCHES FRONTEND)
        # =====================================================
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
                "sentiment_trend": sentiment_trend,
                "keywords": keywords
            }
        }

    except Exception as e:
        print("❌ Dashboard Error:", str(e))
        return {"error": str(e)}


# =========================================================
# 🔹 REVENUE RISK API
# =========================================================
@router.get("/revenue")
async def revenue_analysis(
    company_id: int,
    session: AsyncSession = Depends(get_session)
):
    result = await session.execute(
        select(func.avg(Review.rating)).where(Review.company_id == company_id)
    )
    avg_rating = result.scalar() or 0

    risk_percent = int((5 - avg_rating) * 20)

    impact = "Low"
    if risk_percent > 60:
        impact = "High"
    elif risk_percent > 30:
        impact = "Medium"

    return {
        "risk_percent": risk_percent,
        "impact": impact
    }


# =========================================================
# 🔹 CHATBOT (BASIC)
# =========================================================
@router.get("/chatbot/explain/{company_id}")
async def chatbot_explain(
    company_id: int,
    question: str,
    session: AsyncSession = Depends(get_session)
):
    result = await session.execute(
        select(func.avg(Review.rating)).where(Review.company_id == company_id)
    )
    avg = result.scalar() or 0

    if avg >= 4:
        answer = "Your business is performing well. Focus on scaling."
    elif avg >= 3:
        answer = "Moderate performance. Improve customer experience."
    else:
        answer = "Low ratings detected. Urgent service improvement needed."

    return {"answer": answer}


# =========================================================
# 🔹 DEBUG API (VERY IMPORTANT)
# =========================================================
@router.get("/debug/company/{company_id}")
async def debug_company(
    company_id: int,
    session: AsyncSession = Depends(get_session)
):
    result = await session.execute(
        select(func.count(Review.id)).where(Review.company_id == company_id)
    )

    count = result.scalar()

    return {
        "company_id": company_id,
        "total_reviews": count
    }
