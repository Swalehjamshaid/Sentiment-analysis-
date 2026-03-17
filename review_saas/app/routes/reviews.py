# filename: app/routes/reviews.py
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.core.db import get_session
from app.core.models import Review
from app.services.scraper import FastGoogleScraper
from sqlalchemy import select

router = APIRouter(prefix="/api/reviews", tags=["Reviews"])
scraper = FastGoogleScraper()

@router.post("/ingest/{company_id}")
async def ingest_reviews(company_id: int, limit: Optional[int] = 100, session: AsyncSession = Depends(get_session)):
    """
    Fetch reviews for a company and store in DB.
    Uses FastGoogleScraper.
    """
    # Placeholder: For now, use company_id as place_id
    place_id = str(company_id)

    reviews = await scraper.get_reviews(place_id, limit=limit)

    if not reviews:
        raise HTTPException(status_code=500, detail="No reviews fetched")

    # Fetch existing review_ids for this company to avoid duplicates
    existing_stmt = select(Review.review_id).where(Review.company_id == company_id)
    result = await session.execute(existing_stmt)
    existing_ids = set([r[0] for r in result.fetchall()])

    # Insert new reviews
    new_reviews = []
    for r in reviews:
        if r["review_id"] not in existing_ids:
            new_reviews.append(
                Review(
                    company_id=company_id,
                    review_id=r["review_id"],
                    rating=r["rating"],
                    text=r["text"],
                    author_title=r["author_title"],
                    google_review_time=r["review_datetime_utc"]
                )
            )

    if new_reviews:
        session.add_all(new_reviews)
        await session.commit()

    return {"status": "success", "ingested": len(new_reviews)}
