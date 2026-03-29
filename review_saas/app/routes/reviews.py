import logging
from typing import Dict, Any
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from textblob import TextBlob

# Internal imports
from app.core.models import Review, Company
from app.services.scraper import fetch_reviews

logger = logging.getLogger("app.services.review")

def calculate_sentiment(text: str) -> float:
    """
    Analyzes text to return polarity (-1.0 to 1.0).
    Required for Sentiment Trend and Emotion Radar.
    """
    if not text or text == "No content":
        return 0.0
    try:
        return round(TextBlob(text).sentiment.polarity, 2)
    except Exception as e:
        logger.error(f"Sentiment Analysis Error: {e}")
        return 0.0

async def sync_reviews_for_company(
    session: AsyncSession, 
    company_id: int, 
    target_limit: int = 100
) -> Dict[str, Any]:
    """
    Matches: document.getElementById(\"syncBtn\").onclick
    Endpoint: /api/reviews/ingest/{cid}
    """
    try:
        res = await session.execute(select(Company).where(Company.id == company_id))
        company = res.scalar_one_or_none()
        
        if not company:
            return {"status": "error", "message": "Business not found"}

        # Scrape data using scraper.py logic
        raw_reviews = await fetch_reviews(
            company_id=company_id, 
            session=session, 
            place_id=company.place_id,
            target_limit=target_limit
        )

        new_count = 0
        for r in raw_reviews:
            # Check for existing review_id
            existing = await session.execute(
                select(Review).where(Review.google_review_id == r["google_review_id"])
            )
            if existing.scalar_one_or_none():
                continue

            sentiment = calculate_sentiment(r["text"])

            new_review = Review(
                company_id=company_id,
                google_review_id=r["google_review_id"],
                author_name=r["author_name"],
                rating=r["rating"],
                text=r["text"],
                sentiment_score=sentiment,
                created_at=datetime.utcnow()
            )
            session.add(new_review)
            new_count += 1

        if new_count > 0:
            await session.commit()
            
        # Returns 'reviews_count' to match JavaScript alert
        return {
            "status": "success", 
            "reviews_count": new_count
        }

    except Exception as e:
        await session.rollback()
        logger.error(f"Sync Failure: {e}")
        return {"status": "error", "message": str(e)}

async def get_dashboard_insights(
    session: AsyncSession, 
    company_id: int, 
    start_date: str, 
    end_date: str
) -> Dict[str, Any]:
    """
    Matches: async function triggerAllLoads()
    Endpoint: /api/ai/insights
    """
    # Parse dates from HTML inputs
    start = datetime.strptime(start_date, '%Y-%m-%d')
    end = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1)

    stmt = select(Review).where(
        Review.company_id == company_id,
        Review.created_at >= start,
        Review.created_at <= end
    )
    res = await session.execute(stmt)
    reviews = res.scalars().all()

    total = len(reviews)
    avg_rating = round(sum(r.rating for r in reviews) / total, 1) if total > 0 else 0.0

    # 1. Rating Distribution (Bar Chart: chartRatings)
    # Javascript expects an array ordered from 1* to 5*
    dist = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    for r in reviews:
        dist[r.rating] = dist.get(r.rating, 0) + 1
    
    # 2. Sentiment Trend (Line Chart: chartMonthly)
    trend_map = {}
    for r in reviews:
        day = r.created_at.strftime('%Y-%m-%d')
        if day not in trend_map: trend_map[day] = []
        trend_map[day].append(r.sentiment_score)
    
    sentiment_trend = [
        {"date": d, "avg": round(sum(s)/len(s), 2)} 
        for d, s in sorted(trend_map.items())
    ]

    # 3. Emotions (Radar Chart: chartEmotions)
    # JS expects: Object.keys(vis.emotions)
    emotions = {
        "Positive": len([r for r in reviews if r.sentiment_score > 0.2]),
        "Neutral": len([r for r in reviews if -0.2 <= r.sentiment_score <= 0.2]),
        "Negative": len([r for r in reviews if r.sentiment_score < -0.2]),
        "Urgent": len([r for r in reviews if r.rating <= 2]),
        "Satisfied": len([r for r in reviews if r.rating >= 4])
    }

    # 4. Final Payload Structure (100% match to JS data extraction)
    return {
        "metadata": {
            "total_reviews": total
        },
        "kpis": {
            "benchmark": {
                "your_avg": avg_rating
            },
            "reputation_score": int(avg_rating * 20)
        },
        "visualizations": {
            "ratings": list(dist.values()), # [1*, 2*, 3*, 4*, 5*]
            "sentiment_trend": sentiment_trend,
            "emotions": emotions
        }
    }

async def get_revenue_risk(session: AsyncSession, company_id: int) -> Dict[str, Any]:
    """
    Matches: fetch(`/api/dashboard/revenue?company_id=${cid}`)
    """
    res = await session.execute(select(Review).where(Review.company_id == company_id))
    reviews = res.scalars().all()
    
    total = len(reviews)
    if total == 0:
        return {"risk_percent": 0, "impact": "N/A"}

    negative = len([r for r in reviews if r.rating <= 2])
    risk_pct = int((negative / total) * 100)
    
    return {
        "risk_percent": risk_pct,
        "impact": "CRITICAL" if risk_pct > 25 else "HIGH" if risk_pct > 15 else "LOW"
    }
