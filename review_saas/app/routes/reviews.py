# app/routes/reviews.py

import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime

from app.core.db import get_session
from app.core import models
from app.services.scraper import fetch_reviews

logger = logging.get("app.reviews")

router = APIRouter()


@router.post("/reviews/ingest/{company_id}")
async def ingest_reviews(
    company_id: int,
    db: AsyncSession = Depends(get_session)
):
    logger.info(f"🚀 Sync triggered for company_id={company_id}")

    # 1️⃣ Load company
    result = await db.execute(
        select(models.Company).where(models.Company.id == company_id)
    )
    company = result.scalar_one_or_none()

    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    logger.info(f"🏢 Company loaded: id={company.id}, name='{company.name}'")

    # 2️⃣ Fetch reviews (SCRAPER LOGIC UNCHANGED)
    reviews = await fetch_reviews(
        company_id=company.id,
        session=db
    )

    if not reviews:
        logger.warning("⚠️ No reviews fetched")
        return {
            "status": "warning",
            "reviews_saved": 0
        }

    saved_count = 0

    # 3️⃣ Save reviews (✅ FIXED FIELD MAPPING)
    for r in reviews:
        review_id = r.get("google_review_id")  # ✅ FIX

        if not review_id:
            continue

        existing = await db.execute(
            select(models.Review).where(
                models.Review.review_id == review_id
            )
        )
        if existing.scalar_one_or_none():
            continue

        review = models.Review(
            company_id=company.id,
            review_id=review_id,                       # ✅ FIX
            author=r.get("author_name"),               # ✅ FIX
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


def _parse_date(date_str):
    try:
        return datetime.fromisoformat(date_str) if date_str else datetime.utcnow()
    except Exception:
        return datetime.utcnow()
