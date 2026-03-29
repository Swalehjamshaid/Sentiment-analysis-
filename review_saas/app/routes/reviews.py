import logging
from typing import List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from textblob import TextBlob  # Assuming TextBlob for sentiment as per SaaS goals

from app.core.models import Review, Company
from app.services.scraper import fetch_reviews

logger = logging.getLogger("app.services.review")

def calculate_sentiment(text: str) -> float:
    """
    Calculates a sentiment score between -1.0 (Negative) and 1.0 (Positive).
    """
    if not text or text == "No content":
        return 0.0
    return TextBlob(text).sentiment.polarity

async def sync_reviews_for_company(
    session: AsyncSession, 
    company_id: int, 
    target_limit: int = 100
) -> Dict[str, Any]:
    """
    Orchestrates the scraping, sentiment analysis, and database storage.
    """
    try:
        # 1. Verify Company exists
        res = await session.execute(select(Company).where(Company.id == company_id))
        company = res.scalar_one_or_none()
        
        if not company:
            return {"status": "error", "message": f"Company ID {company_id} not found"}

        # 2. Fetch raw data from the Scraper service
        # Uses the place_id stored in the Company model or falls back to name
        raw_reviews = await fetch_reviews(
            company_id=company_id, 
            session=session, 
            place_id=company.place_id,
            target_limit=target_limit
        )

        if not raw_reviews:
            return {"status": "warning", "message": "No new reviews found via SerpApi"}

        new_count = 0
        for r in raw_reviews:
            # 3. Prevent Duplicates: Check if review already exists
            existing_check = await session.execute(
                select(Review).where(Review.google_review_id == r["google_review_id"])
            )
            if existing_check.scalar_one_or_none():
                continue

            # 4. Perform Sentiment Analysis
            sentiment_score = calculate_sentiment(r["text"])

            # 5. Create Model Instance (Aligned with the Architect doc)
            new_review = Review(
                company_id=company_id,
                google_review_id=r["google_review_id"],
                author_name=r["author_name"],
                rating=r["rating"],
                text=r["text"],
                sentiment_score=sentiment_score,
                # Additional fields from your scraper
                meta={
                    "likes": r.get("likes", 0),
                    "original_date": r.get("google_review_time")
                }
            )
            session.add(new_review)
            new_count += 1

        # 6. Commit changes to Database
        if new_count > 0:
            await session.commit()
            logger.info(f"Successfully synced {new_count} reviews for {company.name}")
        
        return {
            "status": "success", 
            "new_reviews_added": new_count,
            "total_fetched": len(raw_reviews)
        }

    except Exception as e:
        await session.rollback()
        logger.error(f"Failed to sync reviews: {str(e)}")
        return {"status": "error", "message": str(e)}

async def get_dashboard_stats(session: AsyncSession, company_id: int):
    """
    Helper to fetch stats specifically for the Chart.js frontend.
    """
    result = await session.execute(
        select(Review).where(Review.company_id == company_id)
    )
    reviews = result.scalars().all()
    
    return {
        "total": len(reviews),
        "avg_rating": sum(r.rating for r in reviews) / len(reviews) if reviews else 0,
        "sentiment_avg": sum(r.sentiment_score for r in reviews) / len(reviews) if reviews else 0
    }
