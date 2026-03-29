import logging
from typing import Dict, Any, List
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from textblob import TextBlob

# Internal imports
from app.core.models import Review, Company
from app.services.scraper import fetch_reviews

logger = logging.getLogger("app.services.review")

def calculate_sentiment(text: str) -> float:
    """Calculates polarity for Line/Radar charts. Range: -1.0 to 1.0."""
    if not text or text == "No content":
        return 0.0
    try:
        return round(TextBlob(text).sentiment.polarity, 2)
    except Exception:
        return 0.0

async def sync_reviews_for_company(
    session: AsyncSession, 
    company_id: int, 
    target_limit: int = 100
) -> Dict[str, Any]:
    """
    Matched to: document.getElementById("syncBtn").onclick
    Returns: {"reviews_count": int} for the JS alert()
    """
    try:
        res = await session.execute(select(Company).where(Company.id == company_id))
        company = res.scalar_one_or_none()
        if not company:
            return {"status": "error", "message": "Business not found"}

        raw_reviews = await fetch_reviews(
            company_id=company_id, 
            session=session, 
            place_id=company.place_id,
            target_limit=target_limit
        )

        new_count = 0
        for r in raw_reviews:
            # Duplicate check
            stmt = select(Review).where(Review.google_review_id == r["google_review_id"])
            existing = await session.execute(stmt)
            if existing.scalar_one_or_none():
                continue

            new_review = Review(
                company_id=company_id,
                google_review_id=r["google_review_id"],
                author_name=r["author_name"],
                rating=r["rating"],
                text=r["text"],
                sentiment_score=calculate_sentiment(r["text"]),
                created_at=datetime.utcnow()
            )
            session.add(new_review)
            new_count += 1

        await session.commit()
        return {"status": "success", "reviews_count": new_count}

    except Exception as e:
        await session.rollback()
        return {"status": "error", "message": str(e)}

async def get_dashboard_insights(
    session: AsyncSession, 
    company_id: int, 
    start_str: str, 
    end_str: str
) -> Dict[str, Any]:
    """
    Matched to: async function triggerAllLoads()
    Returns keys: metadata, kpis, visualizations (emotions, sentiment_trend, ratings)
    """
    start = datetime.strptime(start_str, '%Y-%m-%d')
    end = datetime.strptime(end_str, '%Y-%m-%d') + timedelta(days=1)

    stmt = select(Review).where(
        Review.company_id == company_id,
        Review.created_at >= start,
        Review.created_at <= end
    )
    res = await session.execute(stmt)
    reviews = res.scalars().all()

    total = len(reviews)
    avg_rating = round(sum(r.rating for r in reviews) / total, 1) if total > 0 else 0.0

    # 1. Bar Chart: Rating Distribution
    dist = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    for r in reviews:
        dist[r.rating] += 1

    # 2. Line Chart: Sentiment Trend
    trend_map = {}
    for r in reviews:
        day = r.created_at.strftime('%Y-%m-%d')
        if day not in trend_map: trend_map[day] = []
        trend_map[day].append(r.sentiment_score)
    
    sentiment_trend = [
        {"date": d, "avg": round(sum(s)/len(s), 2)} 
        for d, s in sorted(trend_map.items())
    ]

    # 3. Radar Chart: Emotions
    emotions = {
        "Positive": len([r for r in reviews if r.sentiment_score > 0.2]),
        "Neutral": len([r for r in reviews if -0.2 <= r.sentiment_score <= 0.2]),
        "Negative": len([r for r in reviews if r.sentiment_score < -0.2]),
        "Critical": len([r for r in reviews if r.rating <= 2]),
        "Satisfaction": len([r for r in reviews if r.rating >= 4])
    }

    return {
        "metadata": {"total_reviews": total},
        "kpis": {
            "benchmark": {"your_avg": avg_rating},
            "reputation_score": int(avg_rating * 20)
        },
        "visualizations": {
            "ratings": list(dist.values()),
            "sentiment_trend": sentiment_trend,
            "emotions": emotions
        }
    }

async def get_revenue_risk_data(session: AsyncSession, company_id: int) -> Dict[str, Any]:
    """
    Matched to: fetch(`/api/dashboard/revenue?company_id=${cid}`)
    Returns keys: risk_percent, impact
    """
    res = await session.execute(select(Review).where(Review.company_id == company_id))
    reviews = res.scalars().all()
    total = len(reviews)
    
    if total == 0:
        return {"risk_percent": 0, "impact": "N/A"}

    neg = len([r for r in reviews if r.rating <= 2])
    risk_pct = int((neg / total) * 100)
    
    return {
        "risk_percent": risk_pct,
        "impact": "CRITICAL" if risk_pct > 25 else "HIGH" if risk_pct > 15 else "STABLE"
    }
