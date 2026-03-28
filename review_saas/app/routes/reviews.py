# filename: app/routes/reviews.py

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List

from app.core.database import get_db
from app.core.models import Review, Company
from app.services.scraper import fetch_reviews

router = APIRouter(prefix="/reviews", tags=["Reviews"])


# =========================
# FETCH + STORE REVIEWS
# =========================
@router.post("/fetch/{company_id}")
async def fetch_and_store_reviews(
    company_id: int,
    limit: int = 100,
    db: AsyncSession = Depends(get_db)
):
    """
    Fetch reviews from SERPAPI and store in DB
    """

    # 1. Validate company
    result = await db.execute(select(Company).where(Company.id == company_id))
    company = result.scalar_one_or_none()

    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    # 2. Fetch from scraper
    scraped_reviews = await fetch_reviews(
        company_id=company_id,
        session=db,
        target_limit=limit
    )

    if not scraped_reviews:
        return {
            "status": "warning",
            "message": "No reviews fetched",
            "inserted": 0
        }

    # 3. Insert into DB (avoid duplicates)
    inserted_count = 0

    for r in scraped_reviews:
        # Check duplicate via google_review_id
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
        "fetched": len(scraped_reviews),
        "inserted": inserted_count
    }


# =========================
# GET REVIEWS BY COMPANY
# =========================
@router.get("/{company_id}", response_model=List[dict])
async def get_reviews(
    company_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Get stored reviews for a company
    """

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


# =========================
# DELETE REVIEWS (OPTIONAL)
# =========================
@router.delete("/{company_id}")
async def delete_reviews(
    company_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Delete all reviews of a company
    """

    result = await db.execute(
        select(Review).where(Review.company_id == company_id)
    )
    reviews = result.scalars().all()

    if not reviews:
        return {"message": "No reviews to delete"}

    for r in reviews:
        await db.delete(r)

    await db.commit()

    return {"status": "deleted", "count": len(reviews)}
