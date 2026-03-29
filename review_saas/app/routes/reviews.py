import logging
from typing import Dict, Any, List
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from textblob import TextBlob

# Internal imports aligned with your project structure
from app.core.models import Review, Company
from app.services.scraper import fetch_reviews

logger = logging.getLogger("app.reviews")

# =====================================================
# 🛠 AI & DATA HELPERS
# =====================================================

def calculate_sentiment(text: str) -> float:
    """
    Calculates polarity score (-1.0 to 1.0).
    Required for Sentiment Trend and Emotion Radar charts.
    """
    if not text or text == "No content":
        return 0.0
    try:
        # Standard sentiment analysis using TextBlob
        analysis = TextBlob(text)
        return round(analysis.sentiment.polarity, 2)
    except Exception as e:
        logger.error(f"Sentiment Analysis Error: {e}")
        return 0.0

# =====================================================
# 🚀 CORE SERVICE FUNCTIONS
# =====================================================

async def sync_reviews_for_company(
    session: AsyncSession, 
    company_id: int, 
    target_limit: int = 100
) -> Dict[str, Any]:
    """
    Orchestrates the scraping and database persistence.
    Matched to: document.getElementById("syncBtn").onclick (HTML)
    """
    try:
        # 1. Load Company
        res = await session.execute(select(Company).where(Company.id == company_id))
        company = res.scalar_one_or_none()
        
        if not company:
            return {"status": "error", "message": "Business entity not found"}

        logger.info(f"🔄 Sync triggered for {company.name}")

        # 2. Fetch raw reviews from Scraper
        # Uses the google_place_id stored in the Company model
        raw_reviews = await fetch_reviews(
            company_id=company_id, 
            session=session, 
            place_id=company.google_place_id,
            target_limit=target_limit
        )

        new_count = 0
        for r in raw_reviews:
            g_id = r.get("google_review_id")
            
            if not g_id:
                continue

            # 3. Duplicate Check
            stmt = select(Review).where(Review.google_review_id == g_id)
            existing = await session.execute(stmt)
            if existing.scalar_one_or_none():
                continue

            # 4. Process Sentiment
            text_body = r.get("text") or "No content"
            sentiment = calculate_sentiment(text_body)

            # 5. Create Model Instance (Aligned with v24.0.7 Schema)
            new_review = Review(
                company_id=company_id,
                google_review_id=g_id,
                author_name=r.get("author_name", "Anonymous"),
                rating=int(r.get("rating", 0)),
                text=text_body,
                sentiment_score=sentiment,
                source_platform="Google",
                # Packs extra SerpApi data into the JSON meta column
                meta={
                    "likes": r.get("likes", 0),
                    "google_time": r.get("google_review_time")
                },
                created_at=datetime.utcnow()
            )
            session.add(new_review)
            new_count += 1

        if new_count > 0:
            await session.commit()
            logger.info(f"✅ Successfully saved {new_count} reviews for {company.name}")
        
        return {
            "status": "success", 
            "reviews_count": new_count
        }

    except Exception as e:
        await session.rollback()
        logger.error(f"❌ Sync Failed: {str(e)}")
        return {"status": "error", "message": str(e)}


async def get_dashboard_insights(
    session: AsyncSession, 
    company_id: int, 
    start_str: str, 
    end_str: str
) -> Dict[str, Any]:
    """
    Prepares data for Chart.js and KPI cards.
    Matched to: async function triggerAllLoads() (HTML)
    """
    # Parse dates from frontend
    try:
        start = datetime.strptime(start_str, '%Y-%m-%d')
        end = datetime.strptime(end_str, '%Y-%m-%d') + timedelta(days=1)
    except ValueError:
        # Fallback to last 30 days if date parsing fails
        end = datetime.utcnow()
        start = end - timedelta(days=30)

    # Fetch reviews in range
    stmt = select(Review).where(
        Review.company_id == company_id,
        Review.created_at >= start,
        Review.created_at <= end
    )
    res = await session.execute(stmt)
    reviews = res.scalars().all()

    total = len(reviews)
    avg_rating = round(sum(r.rating for r in reviews) / total, 1) if total > 0 else 0.0

    # 1. Bar Chart: Rating Distribution (chartRatings)
    # Javascript expects an array ordered from 1* to 5*
    dist = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    for r in reviews:
        dist[r.rating] = dist.get(r.rating, 0) + 1

    # 2. Line Chart: Sentiment Trend (chartMonthly)
    trend_map = {}
    for r in reviews:
        day = r.created_at.strftime('%Y-%m-%d')
        if day not in trend_map: trend_map[day] = []
        trend_map[day].append(r.sentiment_score)
    
    sentiment_trend = [
        {"date": d, "avg": round(sum(s)/len(s), 2)} 
        for d, s in sorted(trend_map.items())
    ]

    # 3. Radar Chart: Emotions (chartEmotions)
    # JS expects: Object.keys(vis.emotions)
    emotions = {
        "Positive": len([r for r in reviews if r.sentiment_score > 0.2]),
        "Neutral": len([r for r in reviews if -0.2 <= r.sentiment_score <= 0.2]),
        "Negative": len([r for r in reviews if r.sentiment_score < -0.2]),
        "Critical": len([r for r in reviews if r.rating <= 2]),
        "Satisfaction": len([r for r in reviews if r.rating >= 4])
    }

    # 100% Match to the JSON structure expected by dashboard.html triggerAllLoads()
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
    Matched to: fetch(`/api/dashboard/revenue?company_id=${cid}`) (HTML)
    """
    res = await session.execute(select(Review).where(Review.company_id == company_id))
    reviews = res.scalars().all()
    total = len(reviews)
    
    if total == 0:
        return {"risk_percent": 0, "impact": "N/A"}

    # Percentage of negative reviews (1-2 stars)
    neg = len([r for r in reviews if r.rating <= 2])
    risk_pct = int((neg / total) * 100)
    
    return {
        "risk_percent": risk_pct,
        "impact": "CRITICAL" if risk_pct > 25 else "HIGH" if risk_pct > 15 else "STABLE"
    }
