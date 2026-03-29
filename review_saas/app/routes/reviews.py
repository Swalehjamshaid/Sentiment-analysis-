# app/routes/reviews.py

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.db import get_session
from app.core import models
from app.services.scraper import fetch_reviews

# ✅ FIX 1: Correct logger initialization
logger = logging.getLogger("app.reviews")

router = APIRouter()


@router.post("/reviews/ingest/{company_id}")
async def ingest_reviews(
    company_id: int,
    db: AsyncSession = Depends(get_session)
):
    """
    Trigger live review sync for a company.
    """

    logger.info(f"🚀 Sync triggered for company_id={company_id}")

    # ✅ FIX 2: Load company safely
    result = await db.execute(
        select(models.Company).where(models.Company.id == company_id)
    )
    company = result.scalar_one_or_none()

    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    logger.info(f"🏢 Company loaded: id={company.id}, name='{company.name}'")

    # ✅ FIX 3: Call scraper (UNCHANGED logic)
    reviews = await fetch_reviews(
        company_id=company.id,
        session=db
    )

    if not reviews:
        logger.warning("⚠️ No reviews fetched from scraper")
        return {
            "status": "warning",
            "reviews_saved": 0
        }

    saved_count = 0

    # ✅ FIX 4: Correct field mapping from scraper → DB
    for r in reviews:
        review_id = r.get("google_review_id")  # ✅ CRITICAL FIX

        if not review_id:
            continue

        # ✅ Skip duplicates
        existing = await db.execute(
            select(models.Review).where(
                models.Review.review_id == review_id
            )
        )
        if existing.scalar_one_or_none():
            continue

        review = models.Review(
            company_id=company.id,
            review_id=review_id,
            author=r.get("author_name"),
            rating=r.get("rating", 5),
            text=r.get("text", ""),
            sentiment=None,
            created_at=_parse_date(r.get("google_review_time"))
        )

        db.add(review)
        saved_count += 1

    await db.commit()

    logger.info(
        f"✅ Sync complete for company_id={company.id}, "
        f"reviews_saved={saved_count}"
    )

    return {
        "status": "success",
        "reviews_saved": saved_count
    }


# ✅ Helper: Safe date parser
def _parse_date(date_str):
    try:
        return datetime.fromisoformat(date_str) if date_str else datetime.utcnow()
    except Exception:
        return datetime.utcnow()
``
