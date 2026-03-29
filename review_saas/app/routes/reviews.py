import logging
from typing import Dict, Any, List
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from textblob import TextBlob

# Internal imports aligned with your core models and scraper
from app.core.models import Review, Company
from app.services.scraper import fetch_reviews

logger = logging.getLogger("app.services.review")

def calculate_sentiment(text: str) -> float:
    """
    Calculates polarity for the Dashboard charts.
    Returns a float between -1.0 (Negative) and 1.0 (Positive).
    """
    if not text or text == "No content":
        return 0.0
    try:
        # Using TextBlob for sentiment analysis as per SaaS requirements
        analysis = TextBlob(text)
        return round(analysis.sentiment.polarity, 2)
    except Exception as e:
        logger.error(f"Sentiment analysis failed: {e}")
        return 0.0

async def sync_reviews_for_company(
    session: AsyncSession, 
    company_id: int, 
    target_limit: int = 100
) -> Dict[str, Any]:
    """
    Orchestrates the scraping and database storage.
    Matched to: document.getElementById("syncBtn").onclick
    """
    try:
        # 1. Get Company details for the Google Place ID
        res = await session.execute(select(Company).where(Company.id == company_id))
        company = res.scalar_one_or_none()
        
        if not company:
            return {"status": "error", "message": "Business entity not found"}

        # 2. Fetch raw reviews from the Scraper service
        raw_reviews = await fetch_reviews(
            company_id=company_id, 
            session=session, 
            place_id=company.place_id,
            target_limit=target_limit
        )

        new_count = 0
        for r in raw_reviews:
            # Prevent Duplicates: Check if google_review_id is already in DB
            existing_check = await session.execute(
                select(Review).where(Review.google_review_id == r["google_review_id"])
            )
            if existing_check.scalar_one_or_none():
                continue

            # Calculate sentiment for the new review
            sentiment = calculate_sentiment(r["text"])

            # Create Database Record
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

        # 3. Finalize transaction
        if new_count > 0:
            await session.commit()
        
        return {
            "status": "success", 
            "reviews_count": new_count
        }

    except Exception as e:
        await session.rollback()
        logger.error(f"Critical Sync Error: {str(e)}")
        return {"status": "error", "message": str(e)}

async def get_dashboard_insights(
    session: AsyncSession, 
    company_id: int, 
    start_str: str, 
    end_str: str
) -> Dict[str, Any]:
    """
    Prepares data for Chart.js and KPI cards.
    Matched to: async function triggerAllLoads()
    """
    # Parse dates from frontend input
    start = datetime.strptime(start_str, '%Y-%m-%d')
    end = datetime.strptime(end_str, '%Y-%m-%d') + timedelta(days=1)

    # Query reviews within the selected date range
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
    # Ordered array [1*, 2*, 3*, 4*, 5*]
    dist = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    for r in reviews:
        dist[r.rating] = dist.get(r.rating, 0) + 1

    # 2. Sentiment Trend (Line Chart: chartMonthly)
    trend_map = {}
    for r in reviews:
        day = r.created_at.strftime('%Y-%m-%d')
        if day not in trend_map:
            trend_map[day] = []
        trend_map[day].append(r.sentiment_score)
    
    sentiment_trend = [
        {"date": d, "avg": round(sum(scores)/len(scores), 2)} 
        for d, scores in sorted(trend_map.items())
    ]

    # 3. Emotions (Radar Chart: chartEmotions)
    emotions = {
        "Positive": len([r for r in reviews if r.sentiment_score > 0.2]),
        "Neutral": len([r for r in reviews if -0.2 <= r.sentiment_score <= 0.2]),
        "Negative": len([r for r in reviews if r.sentiment_score < -0.2]),
        "Critical": len([r for r in reviews if r.rating <= 2]),
        "Satisfaction": len([r for r in reviews if r.rating >= 4])
    }

    # Final Payload matching the JavaScript keys in dashboard.html
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
            "ratings": list(dist.values()),
            "sentiment_trend": sentiment_trend,
            "emotions": emotions
        }
    }

async def get_revenue_risk_data(session: AsyncSession, company_id: int) -> Dict[str, Any]:
    """
    Calculates loss probability for the Risk Monitoring card.
    Matched to: fetch(`/api/dashboard/revenue?company_id=${cid}`)
    """
    res = await session.execute(select(Review).where(Review.company_id == company_id))
    reviews = res.scalars().all()
    
    total = len(reviews)
    if total == 0:
        return {"risk_percent": 0, "impact": "N/A"}

    # Calculate percentage of reviews with 2 stars or less
    neg = len([r for r in reviews if r.rating <= 2])
    risk_pct = int((neg / total) * 100)
    
    return {
        "risk_percent": risk_pct,
        "impact": "CRITICAL" if risk_pct > 25 else "HIGH" if risk_pct > 15 else "STABLE"
    }
