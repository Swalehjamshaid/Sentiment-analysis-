# filename: app/routes/reviews.py

import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
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
    limit: int = 50,
    session: AsyncSession = Depends(get_session)
):
    # 1. Validate Company
    company = await session.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    # Use place_id if google_id is missing
    place_id = company.google_id or company.place_id
    if not place_id:
        raise HTTPException(status_code=400, detail="Missing Google Place ID for this business")

    logger.info(f"🚀 Syncing reviews for {company.name}")

    # 2. Fetch Reviews from Scraper Service
    scraped_data = await fetch_reviews(place_id=place_id, limit=limit)

    if not scraped_data:
        return {
            "status": "success",
            "message": "No reviews fetched (empty response)",
            "new_reviews_added": 0
        }

    new_count = 0

    for item in scraped_data:
        try:
            review_id = item.get("review_id")
            if not review_id:
                continue

            # 3. Duplicate Check
            stmt = select(Review).where(
                and_(
                    Review.company_id == company_id,
                    Review.google_review_id == review_id
                )
            )
            existing = (await session.execute(stmt)).scalar_one_or_none()

            if existing:
                continue

            # 4. Sentiment Analysis
            text = item.get("text", "")
            score = analyzer.polarity_scores(text)["compound"]

            if score > 0.05:
                label = "Positive"
            elif score < -0.05:
                label = "Negative"
            else:
                label = "Neutral"

            # 5. Time Parsing
            raw_time = item.get("google_review_time")
            try:
                review_time = datetime.fromisoformat(raw_time) if raw_time else datetime.utcnow()
            except Exception:
                review_time = datetime.utcnow()

            # 6. Save Review to Database
            new_review = Review(
                company_id=company_id,
                google_review_id=review_id,
                author_name=item.get("author_name", "Google User"),
                rating=item.get("rating", 0),
                text=text,
                google_review_time=review_time,
                sentiment_score=score,
                sentiment_label=label,
                source_platform="Google"
            )

            session.add(new_review)
            new_count += 1

        except Exception as e:
            logger.warning(f"Skipping bad review: {str(e)}")
            continue

    # Commit all changes to Postgres
    await session.commit()

    logger.info(f"✅ {new_count} new reviews added for {company.name}")

    return {
        "status": "success",
        "new_reviews_added": new_count,
        "total_scraped": len(scraped_data)
    }

@router.get("/")
async def get_reviews(company_id: int, session: AsyncSession = Depends(get_session)):
    stmt = select(Review).where(Review.company_id == company_id).order_by(Review.google_review_time.desc())
    res = await session.execute(stmt)
    return res.scalars().all()
