# filename: app/routes/reviews.py
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from datetime import datetime

from app.core.db import get_session
from app.core.models import Company, Review
from app.services.scraper import fetch_reviews
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

router = APIRouter(prefix="/api/reviews", tags=["reviews"])
logger = logging.getLogger(__name__)
analyzer = SentimentIntensityAnalyzer()

@router.post("/ingest/{company_id}")
async def ingest_reviews(company_id: int, session: AsyncSession = Depends(get_session)):
    # 1. Get Company from DB
    company = await session.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company record not found in database")

    # 2. Safety: Check all possible Place ID columns
    place_id = getattr(company, 'place_id', None) or getattr(company, 'google_id', None)
    
    if not place_id:
        logger.error(f"400 Error: Company {company_id} ({company.name}) has NO Place ID stored.")
        raise HTTPException(
            status_code=400, 
            detail="This company has no Google Place ID. Please re-add it using the 'Add Business' button."
        )

    # 3. Calculate how many we already have (Pagination Logic)
    count_stmt = select(func.count(Review.id)).where(Review.company_id == company_id)
    existing_count = (await session.execute(count_stmt)).scalar() or 0
    logger.info(f"Syncing {company.name}. Existing: {existing_count}. Fetching next 300...")

    # 4. Fetch data from Scraper
    scraped_data = await fetch_reviews(place_id=place_id, limit=300, skip=existing_count)

    if not scraped_data:
        return {"status": "success", "message": "No more reviews found on Google.", "new_added": 0}

    new_count = 0
    for item in scraped_data:
        try:
            # 5. Duplicate Check
            stmt = select(Review).where(and_(
                Review.company_id == company_id,
                Review.google_review_id == item["review_id"]
            ))
            if (await session.execute(stmt)).scalar_one_or_none():
                continue

            # 6. Sentiment Analysis
            score = analyzer.polarity_scores(item["text"])["compound"]
            label = "Positive" if score > 0.05 else "Negative" if score < -0.05 else "Neutral"

            # 7. Map to Model (Ensure these field names match your app/core/models.py)
            new_review = Review(
                company_id=company_id,
                google_review_id=item["review_id"],
                author_name=item["author_name"],
                rating=item["rating"],
                text=item["text"],
                google_review_time=datetime.fromisoformat(item["google_review_time"]),
                sentiment_score=score,
                sentiment_label=label,
                source_platform="Google"
            )
            session.add(new_review)
            new_count += 1
        except Exception as e:
            logger.warning(f"Error processing single review: {e}")
            continue

    await session.commit()
    logger.info(f"✅ Success: Added {new_count} reviews for {company.name}")
    
    return {
        "status": "success", 
        "new_reviews_added": new_count,
        "total_now_in_db": existing_count + new_count
    }
