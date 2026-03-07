# File: app/routes/reviews.py

from fastapi import APIRouter, HTTPException, Query, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional, Dict, Any

# Updated imports to match main.py structure
from app.core.db import get_session  # Assuming your session generator is here
from app.core.models import Review, Company # Importing from core.models as seen in main.py
from app.services.google_reviews import OutscraperReviewsService

# Initialize router
router = APIRouter(prefix="/api/reviews", tags=["reviews"])

# Initialize Outscraper service
outscraper_service = OutscraperReviewsService()

# ---------------------------------------------------------
# Ingest reviews for a company
# ---------------------------------------------------------
@router.post("/ingest/{place_id}/{company_id}")
async def ingest_reviews(
    place_id: str,
    company_id: int,
    limit: Optional[int] = Query(500, description="Max number of reviews"),
    db: AsyncSession = Depends(get_session)
):
    try:
        # Async query style
        result = await db.execute(select(Company).filter(Company.id == company_id))
        company = result.scalars().first()
        
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        reviews_data = await outscraper_service.fetch_reviews(place_id, limit=limit)
        saved = 0

        for r in reviews_data:
            review_id = r.get("review_id")
            
            # Check for existing review
            exist_check = await db.execute(
                select(Review).filter(Review.external_review_id == review_id)
            )
            if exist_check.scalars().first():
                continue

            review = Review(
                company_id=company_id,
                external_review_id=review_id,
                author=r.get("author_title"),
                rating=r.get("review_rating"),
                review_text=r.get("review_text"),
                review_date=r.get("review_datetime_utc"),
                sentiment=None
            )
            db.add(review)
            saved += 1

        await db.commit()

        return {
            "status": "success",
            "reviews_fetched": len(reviews_data),
            "reviews_saved": saved
        }

    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to ingest reviews: {str(e)}")

# ---------------------------------------------------------
# Review statistics
# ---------------------------------------------------------
@router.get("/stats/{company_id}")
async def review_stats(company_id: int, db: AsyncSession = Depends(get_session)):
    result = await db.execute(select(Review).filter(Review.company_id == company_id))
    reviews = result.scalars().all()
    
    total = len(reviews)
    if total == 0:
        return {"total_reviews": 0, "avg_rating": 0}

    valid_ratings = [r.rating for r in reviews if r.rating is not None]
    if not valid_ratings:
        return {"total_reviews": total, "avg_rating": 0}
        
    avg_rating = sum(valid_ratings) / len(valid_ratings)
    return {"total_reviews": total, "avg_rating": round(avg_rating, 2)}

# ---------------------------------------------------------
# Dashboard Feed
# ---------------------------------------------------------
@router.get("/feed/{company_id}")
async def get_reviews_feed(
    company_id: int, 
    limit: int = 20, 
    db: AsyncSession = Depends(get_session)
):
    result = await db.execute(
        select(Review)
        .filter(Review.company_id == company_id)
        .order_by(Review.review_date.desc())
        .limit(limit)
    )
    reviews = result.scalars().all()

    return {
        "status": "success",
        "reviews": [
            {
                "id": r.id,
                "author": r.author,
                "rating": r.rating,
                "text": r.review_text,
                "date": r.review_date,
                "sentiment": r.sentiment
            }
            for r in reviews
        ]
    }
