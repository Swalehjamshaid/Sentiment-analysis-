# filename: app/routes/reviews.py

import logging
from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Dict, Any
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# ✅ SAFE IMPORT FIX
try:
    from app.db.database import get_db
    from app.db import models
except ModuleNotFoundError:
    from app.core.db import get_session as get_db
    from app.core import models

from app.services.scraper import fetch_reviews

router = APIRouter(prefix="/api/reviews", tags=["Reviews"])
logger = logging.getLogger(__name__)


@router.post("/ingest/{company_id}")
async def ingest_reviews(company_id: int, db: AsyncSession = Depends(get_db)):
    """
    Fetch reviews and store in Postgres (Async-safe)
    """

    # ✅ FIXED (Async way)
    result = await db.execute(
        select(models.Company).where(models.Company.id == company_id)
    )
    company = result.scalar_one_or_none()

    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    if not company.place_id:
        raise HTTPException(status_code=400, detail="Company missing Google Place ID")

    logger.info(f"🚀 Sync Triggered: {company.name}")

    try:
        total_new_reviews = 0
        total_processed = 0
        skip = 0
        batch_size = 200

        for batch in range(10):

            scraped_data = await fetch_reviews(
                place_id=company.place_id,
                limit=batch_size,
                skip=skip
            )

            if not scraped_data:
                break

            new_count = 0

            for item in scraped_data:
                try:
                    # ✅ Async duplicate check
                    existing_result = await db.execute(
                        select(models.Review).where(
                            models.Review.text == item["text"],
                            models.Review.author_name == item["author_name"],
                            models.Review.company_id == company_id
                        )
                    )
                    existing = existing_result.scalar_one_or_none()

                    if not existing:
                        new_review = models.Review(
                            company_id=company_id,
                            review_id=item["review_id"],
                            rating=item["rating"],
                            text=item["text"],
                            author_name=item["author_name"],
                            google_review_time=item["google_review_time"],
                            created_at=datetime.utcnow()
                        )
                        db.add(new_review)
                        new_count += 1

                except Exception:
                    continue

            await db.commit()

            total_new_reviews += new_count
            total_processed += len(scraped_data)

            if len(scraped_data) < batch_size:
                break

            skip += batch_size

        return {
            "status": "success",
            "company": company.name,
            "reviews_count": total_new_reviews,
            "total_processed": total_processed
        }

    except Exception as e:
        await db.rollback()
        logger.error(f"❌ Error: {str(e)}")

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/list/{company_id}", response_model=List[Dict[str, Any]])
async def get_company_reviews(company_id: int, db: AsyncSession = Depends(get_db)):
    """
    Get all reviews (Async)
    """

    result = await db.execute(
        select(models.Review).where(models.Review.company_id == company_id)
    )
    reviews = result.scalars().all()

    return reviews
