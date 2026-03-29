import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

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
    logger.info(f"🚀 Sync triggered for company_id={company_id}")

    # 1️⃣ Load company
    result = await db.execute(
        select(models.Company).where(models.Company.id == company_id)
    )
    company = result.scalar_one_or_none()

    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    logger.info(f"🏢 Company loaded: id={company.id}, name='{company.name}'")

    # 2️⃣ Fetch reviews from scraper (CID-based)
    reviews = await fetch_reviews(
        company_id=company.id,
        name=company.name,
        session=db
    )

    if not reviews:
        logger.warning("⚠️ No reviews fetched (missing CID or no new reviews)")
        return {
            "status": "warning",
            "reviews_saved": 0
        }

    saved_count = 0

    # 3️⃣ Save reviews safely
    for r in reviews:
        # ✅ CORRECT FIELD MAPPING
        google_review_id = r.get("review_id")

        # ✅ HARD GUARARD (prevents your error)
        if not google_review_id or not str(google_review_id).strip():
            logger.warning(
                f"⚠️ Skipping review with missing google_review_id: {r}"
            )
            continue

        # ✅ De-duplication
        existing = await db.execute(
            select(models.Review).where(
                models.Review.google_review_id == google_review_id
            )
        )
        if existing.scalar_one_or_none():
            continue

        review = models.Review(
            company_id=company.id,
            google_review_id=google_review_id,
            review_url=r.get("review_url"),
            author_name=r.get("author_name", "Anonymous"),
            rating=r.get("rating", 0),
            text=r.get("text", ""),
            source_platform="Google",
            sentiment_label=r.get("sentiment"),
            first_seen_at=_parse_date(r.get("google_review_time"))
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


# =====================================================
# 🛠 HELPER
# =====================================================
def _parse_date(date_str):
    try:
        return datetime.fromisoformat(date_str) if date_str else datetime.utcnow()
    except Exception:
        return datetime.utcnow()
