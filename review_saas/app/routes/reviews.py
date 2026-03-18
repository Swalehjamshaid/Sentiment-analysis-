# filename: app/routes/reviews.py
from __future__ import annotations
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from fastapi import APIRouter, HTTPException, Depends, Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.db import get_session
from app.core.models import Company, Review

router = APIRouter(prefix="/reviews", tags=["Reviews"])
logger = logging.getLogger("app.routes.reviews")


BATCH_SIZE = 200  # Number of reviews per batch


async def fetch_google_reviews(company: Company, last_synced: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """
    Placeholder for actual Google reviews fetching logic.
    This should return a list of review dictionaries.
    """
    # Replace this with your Google Places / API logic
    # Each review dict should match the Review model fields
    # Example:
    reviews = [
        {
            "google_review_id": f"rev_{i}",
            "author_name": f"Author {i}",
            "rating": 5,
            "text": f"Review text {i}",
            "google_review_time": datetime.now(timezone.utc),
            "review_url": f"https://reviews.com/{i}",
        }
        for i in range(1, 1001)  # Simulate 1000 reviews
    ]

    # Filter by last_synced if provided
    if last_synced:
        reviews = [r for r in reviews if r["google_review_time"] > last_synced]

    return reviews


@router.post("/ingest/{company_id}")
async def ingest_reviews(
    company_id: int = Path(..., description="ID of the company to fetch reviews for"),
    db: AsyncSession = Depends(get_session),
):
    # Fetch company
    result = await db.execute(select(Company).where(Company.id == company_id))
    company: Optional[Company] = result.scalars().first()

    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    if not company.google_place_id:
        raise HTTPException(status_code=400, detail="Company does not have a Google Place ID")

    logger.info(f"Fetching reviews for company {company.name} (ID {company.id})")

    last_synced = company.last_synced_at
    reviews_data = await fetch_google_reviews(company, last_synced=last_synced)

    if not reviews_data:
        return {"message": "No new reviews found"}

    total_reviews = len(reviews_data)
    logger.info(f"Total new reviews to ingest: {total_reviews}")

    # Batch insertion
    for i in range(0, total_reviews, BATCH_SIZE):
        batch = reviews_data[i:i + BATCH_SIZE]
        logger.info(f"Processing batch {i // BATCH_SIZE + 1}")

        review_objects = []
        for r in batch:
            review_objects.append(
                Review(
                    company_id=company.id,
                    google_review_id=r["google_review_id"],
                    author_name=r.get("author_name"),
                    rating=r.get("rating"),
                    text=r.get("text"),
                    google_review_time=r.get("google_review_time"),
                    review_url=r.get("review_url"),
                    review_photos=r.get("review_photos"),
                    review_videos=r.get("review_videos"),
                )
            )

        db.add_all(review_objects)
        await db.commit()

    # Update last_synced_at
    company.last_synced_at = datetime.now(timezone.utc)
    db.add(company)
    await db.commit()

    logger.info(f"Successfully ingested {total_reviews} reviews for company {company.name}")
    return {"message": f"Successfully ingested {total_reviews} reviews"}
