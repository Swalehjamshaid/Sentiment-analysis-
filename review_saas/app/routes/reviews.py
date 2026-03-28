# filename: app/routes/reviews.py

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List

from app.core.db import get_session
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
    db: AsyncSession = Depends(get_session)
):
    result = await db.execute(select(Company).where(Company.id == company_id))
    company = result.scalar_one_or_none()

    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

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
        "fetched": len(scraped_reviews),
        "inserted": inserted_count
    }


# =========================
# GET REVIEWS
# =========================
@router.get("/{company_id}", response_model=List[dict])
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
