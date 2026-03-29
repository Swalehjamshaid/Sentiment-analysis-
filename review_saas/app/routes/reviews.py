from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime

from app.core.db import get_session
from app.core import models

# ✅ Correct import (FUNCTION, not CLASS)
from app.services.scraper import fetch_reviews

router = APIRouter()


# =====================================================
# 🚀 INGEST REVIEWS (CONNECTED TO FRONTEND SYNC BUTTON)
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

    try:
        # 1️⃣ Get company
        result = await db.execute(
            select(models.Company).where(models.Company.id == company_id)
        )
        company = result.scalar_one_or_none()

        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        # ❗ No place_id check anymore
        # CID is resolved internally by the scraper

        # 2️⃣ Run scraper (CID‑based)
        reviews_data = await fetch_reviews(
            company_id=company.id,
            name=company.name,
            session=db
        )

        if not reviews_data:
            return {
                "status": "success",
                "reviews_count": 0,
                "message": "No new reviews found"
            }

        # 3️⃣ Insert into DB (avoid duplicates)
        saved_count = 0

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
            saved_count += 1

        await db.commit()

        return {
            "status": "success",
            "reviews_count": saved_count
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Review ingestion failed: {str(e)}"
        )


# =====================================================
# 📊 GET REVIEWS (FOR DEBUG / UI)
# =====================================================
@router.get("/reviews/{company_id}")
async def get_reviews(
    company_id: int,
    db: AsyncSession = Depends(get_session)
):
    try:
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

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =====================================================
# 🛠 HELPER: DATE PARSER
# =====================================================
def _parse_date(date_str):
    try:
        if not date_str:
            return datetime.utcnow()
        return datetime.fromisoformat(date_str)
    except Exception:
        return datetime.utcnow()
