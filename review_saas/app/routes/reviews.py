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

@router.post("/ingest/{company_id}", response_model=None)
async def ingest_reviews(
    company_id: int, 
    session: AsyncSession = Depends(get_session)
):
    # 1. Fetch Company from DB
    company = await session.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    # 2. MATCH THE MODEL: Use 'google_place_id' as defined in your models.py
    place_id = company.google_place_id or company.google_id
    
    if not place_id:
        logger.error(f"400 Error: Company {company_id} is missing google_place_id")
        raise HTTPException(
            status_code=400, 
            detail="Google Place ID is missing. Please re-add this business."
        )

    # 3. Pagination Logic
    count_stmt = select(func.count(Review.id)).where(Review.company_id == company_id)
    result = await session.execute(count_stmt)
    existing_count = result.scalar() or 0

    # 4. Fetch from Scraper
    scraped_data = await fetch_reviews(place_id=place_id, limit=300, skip=existing_count)

    if not scraped_data:
        return {"status": "success", "new_reviews_added": 0}

    new_count = 0
    for item in scraped_data:
        try:
            # Duplicate check
            stmt = select(Review).where(and_(
                Review.company_id == company_id,
                Review.google_review_id == item["review_id"]
            ))
            existing = await session.execute(stmt)
            if existing.scalar_one_or_none():
                continue

            # Sentiment Analysis
            score = analyzer.polarity_scores(item["text"])["compound"]
            label = "Positive" if score > 0.05 else "Negative" if score < -0.05 else "Neutral"

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
        except Exception:
            continue

    await session.commit()
    return {"status": "success", "new_reviews_added": new_count}
