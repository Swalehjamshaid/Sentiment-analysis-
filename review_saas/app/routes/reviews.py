# app/routes/reviews.py

import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime

from app.core.db import get_session
from app.core import models
from app.services.scraper import fetch_reviews

logger = logging.getLogger("app.reviews")

router = APIRouter()


# =====================================================
# 🚀 INGEST REVIEWS (SYNC BUTTON)
# =====================================================
@router.post("/reviews/ingest/{company_id}")
async def ingest_reviews(
    company_id: int,
    db: AsyncSession = Depends(get_session)
):
    """
    FRONTEND → Sync Live Data button
    POST /api/reviews/ingest/{company_id}
    """

    # ✅ LOG EVERY TRIGGER (THIS FIXES YOUR ISSUE)
    logger.info(f"🚀 Sync triggered for company_id={company_id}")

    try:
        # 1️⃣ Load company
        result = await db.execute(
            select(models.Company).where(models.Company.id == company_id)
        )
        company = result.scalar_one_or_none()

        if not company:
            logger.warning(f"❌ Company not found: {company_id}")
            raise HTTPException(status_code=404, detail="Company not found")

        logger.info(
            f"🏢 Company loaded: id={company.id}, name='{company.name}'"
        )

        # 2️⃣ Run scraper (CID-based)
        reviews_data = await fetch_reviews(
            company_id=company.id,
            name=company.name,
            session=db
        )

        # ✅ IF NO REVIEWS, EXPLAIN WHY
        if not reviews_data:
            logger.warning(
                f"⚠️ No reviews fetched for company_id={company.id}. "
                f"Likely missing CID in company_cids table."
            )
            return {
                "status": "warning",
                "reviews_count": 0,
                "message": (
                    "Sync executed but no reviews were fetched. "
                    "Check if Google CID is configured for this company."
                )
            }

        # 3️⃣ Insert reviews (deduplicated)
        saved = 0

        for r in reviews_data:
            review_id = r.get("review_id")
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
                review_id=review_id,
                author=r.get("author_name", "Anonymous"),
                rating=r.get("rating", 0),
                text=r.get("text", ""),
                sentiment=r.get("sentiment"),
                created_at=_parse_date(r.get("date"))
            )

            db.add(review)
            saved += 1

        await db.commit()

        logger.info(
            f"✅ Sync complete for company_id={company.id}, "
            f"reviews_saved={saved}"
        )

        return {
            "status": "success",
            "reviews_count": saved
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("❌ Review ingestion failed")
        raise HTTPException(
            status_code=500,
            detail="Review ingestion failed"
        )


# =====================================================
# 📊 GET REVIEWS
# =====================================================
@router.get("/reviews/{company_id}")
async def get_reviews(
    company_id: int,
    db: AsyncSession = Depends(get_session)
):
    result = await db.execute(
        select(models.Review).where(
            models.Review.company_id == company_id
        )
    )
    reviews = result.scalars().all()

    return [
        {
            "id": r.id,
            "author": r.author,
            "rating": r.rating,
            "text": r.text,
            "sentiment": r.sentiment,
            "date": r.created_at
        }
        for r in reviews
    ]


# =====================================================
# 🛠 HELPER
# =====================================================
def _parse_date(date_str):
    try:
        if not date_str:
            return datetime.utcnow()
        return datetime.fromisoformat(date_str)
    except Exception:
        return datetime.utcnow()
