# filename: app/routes/reviews.py
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime

from app.core.db import get_session
from app.core.models import Company, Review
from app.services.scraper_service import FastGoogleScraper
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

router = APIRouter(prefix="/api/reviews", tags=["reviews"])
logger = logging.getLogger(__name__)
analyzer = SentimentIntensityAnalyzer()
scraper = FastGoogleScraper()

@router.post("/ingest/{company_id}")
async def ingest_reviews(company_id: int, limit: int = 50, session: AsyncSession = Depends(get_session)):
    # 1. Verify Company and get Google Data ID
    company = await session.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    
    # Assuming your company model stores the Google ID/CID in a field called 'google_id'
    # If it's stored in the URL, you'll need to parse it first
    data_id = company.google_id 
    if not data_id:
        raise HTTPException(status_code=400, detail="Company does not have a valid Google Data ID")

    # 2. Fetch data using the Fast Scraper
    logger.info(f"🚀 Starting fast scrape for {company.name} (Limit: {limit})")
    scraped_data = await scraper.get_reviews(data_id=data_id, limit=limit)
    
    if not scraped_data:
        return {"status": "success", "message": "No new reviews found or scraper blocked."}

    new_count = 0
    for item in scraped_data:
        # 3. Check if review already exists to avoid duplicates
        stmt = select(Review).where(Review.google_review_id == item["review_id"])
        existing = (await session.execute(stmt)).scalar_one_or_none()
        
        if not existing:
            # 4. Perform local Sentiment Analysis before saving
            sentiment_score = analyzer.polarity_scores(item["text"])["compound"]
            
            label = "Neutral"
            if sentiment_score > 0.05: label = "Positive"
            elif sentiment_score < -0.05: label = "Negative"

            # 5. Create Database Object
            new_review = Review(
                company_id=company_id,
                google_review_id=item["review_id"],
                author_name=item["author_title"],
                rating=item["rating"],
                text=item["text"],
                google_review_time=datetime.fromisoformat(item["review_datetime_utc"]),
                sentiment_score=sentiment_score,
                sentiment_label=label,
                # Add extra fields if your model supports them:
                # author_image=item["author_image"],
                # owner_response=item["owner_answer"]
            )
            session.add(new_review)
            new_count += 1

    # 6. Commit all changes
    try:
        await session.commit()
        logger.info(f"✅ Ingested {new_count} new reviews for {company.name}")
    except Exception as e:
        await session.rollback()
        logger.error(f"Database Error during ingestion: {e}")
        raise HTTPException(status_code=500, detail="Failed to save reviews to database")

    return {
        "status": "success",
        "company": company.name,
        "new_reviews_added": new_count,
        "total_scraped": len(scraped_data)
    }
