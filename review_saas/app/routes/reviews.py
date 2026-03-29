import logging
import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from textblob import TextBlob

# Internal imports aligned with your project structure
from app.core.models import Review, Company
from app.services.scraper import fetch_reviews

logger = logging.getLogger("app.services.review")

def calculate_sentiment(text: str) -> float:
    """
    Analyzes text to return a polarity score between -1.0 and 1.0.
    Used for the Dashboard Sentiment doughnut chart.
    """
    if not text or text == "No content":
        return 0.0
    try:
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
    Main orchestration service:
    1. Fetches raw data from SerpApi via scraper.py
    2. Filters out existing reviews using google_review_id
    3. Calculates sentiment for new reviews
    4. Saves to database and commits session
    """
    try:
        # Step 1: Fetch Company details to get the stored place_id
        stmt = select(Company).where(Company.id == company_id)
        result = await session.execute(stmt)
        company = result.scalar_one_or_none()
        
        if not company:
            return {"status": "error", "message": f"Company ID {company_id} not found"}

        logger.info(f"🔄 Starting sync for {company.name} (ID: {company_id})")

        # Step 2: Get raw review data from Scraper
        # Pass the company.place_id if it exists, otherwise scraper falls back to name
        raw_data = await fetch_reviews(
            company_id=company_id, 
            session=session, 
            place_id=company.place_id,
            target_limit=target_limit
        )

        if not raw_data:
            return {
                "status": "success", 
                "message": "No reviews found or rate limited", 
                "new_reviews_added": 0
            }

        new_count = 0
        added_reviews = []

        # Step 3: Process each review
        for r in raw_data:
            google_id = r.get("google_review_id")
            
            # Duplicate Check: Only add if google_review_id isn't in DB
            dup_stmt = select(Review).where(Review.google_review_id == google_id)
            dup_result = await session.execute(dup_stmt)
            if dup_result.scalar_one_or_none():
                continue

            # Calculate Sentiment
            review_text = r.get("text", "No content")
            sentiment = calculate_sentiment(review_text)

            # Map to SQLAlchemy Model (as per Architect doc)
            new_review = Review(
                company_id=company_id,
                google_review_id=google_id,
                author_name=r.get("author_name"),
                rating=r.get("rating", 5),
                text=review_text,
                sentiment_score=sentiment,
                # Store extra data like likes in a JSON 'meta' column if it exists
                # Or use created_at from the scraper date string
                created_at=datetime.utcnow() 
            )
            
            session.add(new_review)
            added_reviews.append(new_review)
            new_count += 1

        # Step 4: Finalize Database Transaction
        if new_count > 0:
            await session.commit()
            logger.info(f"✅ Successfully added {new_count} new reviews for {company.name}")
        else:
            logger.info(f"ℹ️ No new reviews to add for {company.name}")

        return {
            "status": "success",
            "company_name": company.name,
            "new_reviews_added": new_count,
            "total_processed": len(raw_data)
        }

    except Exception as e:
        await session.rollback()
        logger.error(f"❌ Critical error in sync_reviews_for_company: {str(e)}")
        return {"status": "error", "message": f"Sync failed: {str(e)}"}

async def get_review_metrics(session: AsyncSession, company_id: int) -> Dict[str, Any]:
    """
    Retrieves summary metrics for a company to feed the frontend cards.
    """
    stmt = select(Review).where(Review.company_id == company_id)
    result = await session.execute(stmt)
    reviews = result.scalars().all()
    
    if not reviews:
        return {"total": 0, "average_rating": 0, "sentiment": "N/A"}
        
    avg_rating = sum(r.rating for r in reviews) / len(reviews)
    avg_sentiment = sum(r.sentiment_score for r in reviews) / len(reviews)
    
    return {
        "total": len(reviews),
        "average_rating": round(avg_rating, 2),
        "average_sentiment": round(avg_sentiment, 2)
    }
