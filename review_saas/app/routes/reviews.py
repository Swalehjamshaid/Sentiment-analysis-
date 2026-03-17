import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from datetime import datetime, timezone

from app.core.db import get_session
from app.core.models import Company, Review
from app.services.scraper import FastGoogleScraper
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

router = APIRouter(prefix="/api/reviews", tags=["reviews"])
logger = logging.getLogger(__name__)
analyzer = SentimentIntensityAnalyzer()
scraper = FastGoogleScraper()

@router.post("/ingest/{company_id}")
async def ingest_reviews(
    company_id: int, 
    limit: int = 10000, 
    session: AsyncSession = Depends(get_session)
):
    # 1. Verify Company
    company = await session.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    
    if not company.google_id:
        raise HTTPException(status_code=400, detail="Company is missing Google ID (0x...)")

    # 2. Fetch Data
    logger.info(f"🚀 Syncing {company.name}...")
    scraped_data = await scraper.get_reviews(data_id=company.google_id, limit=limit)
    
    if not scraped_data:
        return {"status": "success", "message": "No new reviews found."}

    new_count = 0
    for item in scraped_data:
        # 3. Prevent Duplicates
        stmt = select(Review).where(
            and_(Review.company_id == company_id, Review.google_review_id == item["review_id"])
        )
        existing = (await session.execute(stmt)).scalar_one_or_none()
        
        if not existing:
            # 4. Sentiment Analysis
            text = item["text"]
            score = analyzer.polarity_scores(text)["compound"]
            label = "Positive" if score > 0.05 else ("Negative" if score < -0.05 else "Neutral")

            # 5. Save to DB
            new_review = Review(
                company_id=company_id,
                google_review_id=item["review_id"],
                author_name=item["author_title"],
                rating=item["rating"],
                text=text,
                google_review_time=datetime.fromisoformat(item["review_datetime_utc"]),
                sentiment_score=score,
                sentiment_label=label,
                source_platform="Google"
            )
            session.add(new_review)
            new_count += 1

    await session.commit()
    logger.info(f"✅ Added {new_count} reviews for {company.name}")
    
    return {
        "status": "success",
        "new_reviews_added": new_count,
        "total_scraped": len(scraped_data)
    }
