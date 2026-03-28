# filename: app/routes/reviews.py

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.db import get_session
from app.core.models import Review, Company
from app.services.scraper import fetch_reviews

router = APIRouter(prefix="/reviews", tags=["Reviews"])


# =========================
# INGEST REVIEWS (MAIN API USED BY DASHBOARD)
# =========================
@router.post("/ingest/{company_id}")
async def ingest_reviews(
    company_id: int,
    limit: int = 100,
    db: AsyncSession = Depends(get_session)
):
    """
    Dashboard Trigger:
    Fetch reviews from SERPAPI and store in DB
    """

    # 1. Validate company
    result = await db.execute(select(Company).where(Company.id == company_id))
    company = result.scalar_one_or_none()

    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    # 2. Fetch reviews using your scraper
    scraped_reviews = await fetch_reviews(
        company_id=company_id,
        session=db,
        place_id=company.place_id,  # IMPORTANT (uses Google Place ID)
        target_limit=limit
    )

    if not scraped_reviews:
        return {
            "status": "warning",
            "reviews_count": 0,
            "inserted": 0,
            "message": "No reviews fetched"
        }

    # 3. Insert into DB (avoid duplicates)
    inserted_count = 0

    for r in scraped_reviews:
        existing = await db.execute(
            select(Review).where(
                Review.google_review_id == r["google_review_id"]
            )
        )

        if existing.scalar_one_or_none():
            continue

        new_review = Review(
            company_id=company_id,
            google_review_id=r["google_review_id"],
            author_name=r["author_name"],
            rating=r["rating"],
            text=r["text"],
            google_review_time=r["google_review_time"],
            likes=r["likes"]
        )

        db.add(new_review)
        inserted_count += 1

    await db.commit()

    return {
        "status": "success",
        "reviews_count": len(scraped_reviews),  # frontend uses this
        "inserted": inserted_count
    }


# =========================
# GET REVIEWS (OPTIONAL)
# =========================
@router.get("/{company_id}")
async def get_reviews(
    company_id: int,
    db: AsyncSession = Depends(get_session)
):
    result = await db.execute(
        select(Review).where(Review.company_id == company_id)
    )
    reviews = result.scalars().all()

    return [
        {
            "id": r.id,
            "author_name": r.author_name,
            "rating": r.rating,
            "text": r.text,
            "date": r.google_review_time,
            "likes": r.likes
        }
        for r in reviews
    ]
