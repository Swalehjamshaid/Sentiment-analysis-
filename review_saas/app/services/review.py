import logging
from typing import Dict, Any, List
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from textblob import TextBlob

# Internal imports
from app.core.models import Review, Company
from app.services.scraper import fetch_reviews

logger = logging.getLogger("app.reviews")

def calculate_sentiment(text: str) -> float:
    """Calculates polarity score (-1.0 to 1.0) for charts."""
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
    """Scraper -> Sentiment -> Postgres Mapping."""
    try:
        # 1. Load Company
        res = await session.execute(select(Company).where(Company.id == company_id))
        company = res.scalar_one_or_none()
        if not company:
            return {"status": "error", "message": "Business not found"}

        # 2. Fetch from SerpApi Scraper
        raw_reviews = await fetch_reviews(
            company_id=company_id, 
            session=session, 
            place_id=company.google_place_id,
            target_limit=target_limit
        )

        new_count = 0
        for r in raw_reviews:
            g_id = r.get("google_review_id")
            if not g_id: continue

            # 3. Duplicate Check
            stmt = select(Review).where(Review.google_review_id == g_id)
            existing = await session.execute(stmt)
            if existing.scalar_one_or_none(): continue

            # 4. Save to EXISTING model (No 'meta' column used here)
            sentiment = calculate_sentiment(r.get("text", ""))
            new_review = Review(
                company_id=company_id,
                google_review_id=g_id,
                author_name=r.get("author_name", "Anonymous"),
                rating=int(r.get("rating", 0)),
                text=r.get("text", "No content"),
                sentiment_score=sentiment,
                source_platform="Google",
                # Map likes to your existing review_likes column
                review_likes=r.get("likes", 0), 
                created_at=datetime.utcnow()
            )
            session.add(new_review)
            new_count += 1

        if new_count > 0:
            await session.commit()
            logger.info(f"✅ Saved {new_count} reviews to Postgres for {company.name}")
        
        return {"status": "success", "reviews_count": new_count}

    except Exception as e:
        await session.rollback()
        logger.error(f"❌ Sync failed: {e}")
        return {"status": "error", "message": str(e)}

async def get_dashboard_insights(
    session: AsyncSession, 
    company_id: int, 
    start_str: str, 
    end_str: str
) -> Dict[str, Any]:
    """Visualization logic for dashboard.html"""
    try:
        start = datetime.strptime(start_str, '%Y-%m-%d')
        end = datetime.strptime(end_str, '%Y-%m-%d') + timedelta(days=1)
    except:
        end = datetime.utcnow()
        start = end - timedelta(days=30)

    stmt = select(Review).where(
        Review.company_id == company_id,
        Review.created_at >= start,
        Review.created_at <= end
    )
    res = await session.execute(stmt)
    reviews = res.scalars().all()

    total = len(reviews)
    avg_rating = round(sum(r.rating for r in reviews) / total, 1) if total > 0 else 0.0

    dist = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    for r in reviews: dist[r.rating] += 1

    emotions = {
        "Positive": len([r for r in reviews if r.sentiment_score > 0.2]),
        "Neutral": len([r for r in reviews if -0.2 <= r.sentiment_score <= 0.2]),
        "Negative": len([r for r in reviews if r.sentiment_score < -0.2]),
        "Critical": len([r for r in reviews if r.rating <= 2]),
        "Satisfaction": len([r for r in reviews if r.rating >= 4])
    }

    return {
        "metadata": {"total_reviews": total},
        "kpis": {"benchmark": {"your_avg": avg_rating}, "reputation_score": int(avg_rating * 20)},
        "visualizations": {
            "ratings": list(dist.values()), 
            "sentiment_trend": [], 
            "emotions": emotions
        }
    }
