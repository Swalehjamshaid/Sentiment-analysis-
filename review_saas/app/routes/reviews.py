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
    company = await session.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    place_id = company.google_id or company.place_id
    if not place_id:
        raise HTTPException(status_code=400, detail="Missing Google Place ID")

    # Count current reviews to set the pagination offset
    count_stmt = select(func.count(Review.id)).where(Review.company_id == company_id)
    existing_count = (await session.execute(count_stmt)).scalar() or 0

    # Fetch next batch of 300
    scraped_data = await fetch_reviews(place_id=place_id, limit=300, skip=existing_count)

    new_count = 0
    for item in scraped_data:
        try:
            # Check for duplicates using the google_review_id
            stmt = select(Review).where(and_(
                Review.company_id == company_id,
                Review.google_review_id == item["review_id"]
            ))
            if (await session.execute(stmt)).scalar_one_or_none(): continue

            score = analyzer.polarity_scores(item["text"])["compound"]
            label = "Positive" if score > 0.05 else "Negative" if score < -0.05 else "Neutral"

            session.add(Review(
                company_id=company_id,
                google_review_id=item["review_id"],
                author_name=item["author_name"],
                rating=item["rating"],
                text=item["text"],
                google_review_time=datetime.fromisoformat(item["google_review_time"]),
                sentiment_score=score,
                sentiment_label=label,
                source_platform="Google"
            ))
            new_count += 1
        except: continue

    await session.commit()
    return {"status": "success", "new_reviews_added": new_count}
