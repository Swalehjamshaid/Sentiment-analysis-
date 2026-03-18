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
async def ingest_reviews(
    company_id: int,
    session: AsyncSession = Depends(get_session)
):
    # 1. Validate Company
    company = await session.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    # 2. Use google_id or place_url (align with existing DB)
    place_id = company.google_id or company.place_url
    if not place_id:
        raise HTTPException(
            status_code=400,
            detail="Missing Google Place ID or URL in the database"
        )

    # 3. Count existing reviews to determine the offset
    count_stmt = select(func.count(Review.id)).where(Review.company_id == company_id)
    existing_count = (await session.execute(count_stmt)).scalar() or 0
    logger.info(f"Existing reviews for {company.name}: {existing_count}. Fetching next batch starting at {existing_count}.")

    # 4. Fetch the next batch of reviews (limit=300)
    scraped_data = await fetch_reviews(place_id=place_id, limit=300, skip=existing_count)
    if not scraped_data:
        return {"status": "success", "message": "No new reviews found in this batch.", "new_reviews_added": 0}

    # 5. Process each review
    new_count = 0
    for item in scraped_data:
        try:
            review_id = item.get("review_id")

            # Skip duplicates
            stmt = select(Review).where(and_(
                Review.company_id == company_id,
                Review.google_review_id == review_id
            ))
            existing = (await session.execute(stmt)).scalar_one_or_none()
            if existing:
                continue

            # Sentiment analysis
            text = item.get("text", "")
            score = analyzer.polarity_scores(text)["compound"]
            label = "Positive" if score > 0.05 else "Negative" if score < -0.05 else "Neutral"

            # Save review
            new_review = Review(
                company_id=company_id,
                google_review_id=review_id,
                author_name=item.get("author_name", "Google User"),
                rating=item.get("rating", 0),
                text=text,
                google_review_time=datetime.fromisoformat(item["google_review_time"]),
                sentiment_score=score,
                sentiment_label=label,
                source_platform="Google"
            )
            session.add(new_review)
            new_count += 1
        except Exception as e:
            logger.warning(f"Skipping a review due to error: {e}")
            continue

    # Commit all new reviews
    await session.commit()

    return {
        "status": "success",
        "new_reviews_added": new_count,
        "current_total_in_db": existing_count + new_count,
        "batch_limit": 300
    }
