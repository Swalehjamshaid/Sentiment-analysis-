# app/routes/reviews.py

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime

from app.core.db import get_session
from app.core import models

# IMPORTANT: adjust this import if your scraper path is different
from app.services.scraper import ReviewScraper

router = APIRouter()


# =====================================================
# 🚀 INGEST REVIEWS (CONNECTED TO FRONTEND SYNC BUTTON)
# =====================================================
@router.post("/reviews/ingest/{company_id}")
async def ingest_reviews(company_id: int, db: AsyncSession = Depends(get_session)):
    """
    Called by:
    FRONTEND → Sync Live Data button

    Endpoint:
    POST /api/reviews/ingest/{company_id}
    """

    try:
        # 1. Get company
        result = await db.execute(
            select(models.Company).where(models.Company.id == company_id)
        )
        company = result.scalar_one_or_none()

        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        if not company.place_id:
            raise HTTPException(status_code=400, detail="Missing place_id")

        # 2. Run scraper
        scraper = ReviewScraper()
        reviews_data = await scraper.fetch_reviews(company.place_id)

        if not reviews_data:
            return {
                "status": "success",
                "reviews_count": 0,
                "message": "No new reviews found"
            }

        # 3. Insert into DB (avoid duplicates)
        saved_count = 0

        for r in reviews_data:
            review_id = r.get("review_id")

            # Check duplicate
            existing = await db.execute(
                select(models.Review).where(models.Review.review_id == review_id)
            )
            if existing.scalar_one_or_none():
                continue

            review = models.Review(
                company_id=company.id,
                review_id=review_id,
                author=r.get("author"),
                rating=r.get("rating", 0),
                text=r.get("text", ""),
                sentiment=r.get("sentiment", 0),
                created_at=_parse_date(r.get("date"))
            )

            db.add(review)
            saved_count += 1

        await db.commit()

        return {
            "status": "success",
            "reviews_count": saved_count
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =====================================================
# 📊 OPTIONAL: GET REVIEWS (FOR DEBUG / EXTENSIONS)
# =====================================================
@router.get("/reviews/{company_id}")
async def get_reviews(company_id: int, db: AsyncSession = Depends(get_session)):
    try:
        result = await db.execute(
            select(models.Review).where(models.Review.company_id == company_id)
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
    except:
        return datetime.utcnow()
