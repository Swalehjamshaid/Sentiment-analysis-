# File: app/routes/reviews.py

from fastapi import APIRouter, HTTPException, Query, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional, Dict, Any
from collections import Counter
from datetime import datetime

from app.core.db import get_session
from app.core.models import Review, Company
from app.services.google_reviews import OutscraperReviewsService, ReviewData

# ---------------------------------------------------------
# Mock API client for testing (replace with real API client)
# ---------------------------------------------------------
class MockClient:
    def get_reviews(self, place_id, limit, offset):
        # Return sample data for testing
        return {
            "reviews": [
                {
                    "review_id": f"rev_{offset+i}",
                    "author_name": f"Author {i}",
                    "rating": 4 + i % 2,
                    "text": f"This is sample review {i}",
                    "time": 1700000000 + i * 1000,
                    "title": f"Title {i}",
                    "helpful_votes": i % 3,
                    "platform": "Google",
                    "competitor_name": f"Competitor {i%2}" if i % 2 == 0 else None
                } for i in range(limit)
            ]
        }

# Initialize API client and Outscraper service
api_client = MockClient()  # Replace with real API client, e.g., OutscraperAPIClient(api_key="YOUR_KEY")
outscraper_service = OutscraperReviewsService(api_client)

# Initialize router
router = APIRouter(prefix="/api/reviews", tags=["reviews"])

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
        # Get company from DB
        result = await db.execute(select(Company).filter(Company.id == company_id))
        company = result.scalars().first()
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        # Fetch reviews from Outscraper service
        reviews_data: List[ReviewData] = await outscraper_service.fetch_reviews(place_id, max_reviews=limit)
        saved = 0

        for r in reviews_data:
            review_id = r.review_id

            # Check if review already exists
            exist_check = await db.execute(
                select(Review).filter(Review.external_review_id == review_id)
            )
            if exist_check.scalars().first():
                continue

            review = Review(
                company_id=company_id,
                external_review_id=review_id,
                author=r.author_name,
                rating=r.rating,
                review_text=r.text,
                review_date=r.time_created,
                sentiment=None,
                competitor_name=r.competitor_name
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
# Review statistics including rating distribution and AI summary
# ---------------------------------------------------------
@router.get("/stats/{company_id}")
async def review_stats(company_id: int, db: AsyncSession = Depends(get_session)):
    result = await db.execute(select(Review).filter(Review.company_id == company_id))
    reviews: List[Review] = result.scalars().all()

    total = len(reviews)
    if total == 0:
        return {"total_reviews": 0, "avg_rating": 0, "rating_distribution": {}, "ai_summary": ""}

    valid_ratings = [r.rating for r in reviews if r.rating is not None]
    avg_rating = sum(valid_ratings) / len(valid_ratings) if valid_ratings else 0

    # Rating distribution
    rating_counts = Counter(r.rating for r in reviews if r.rating is not None)
    rating_distribution = {i: rating_counts.get(i, 0) for i in range(1, 6)}

    # AI summary placeholder (replace with real AI summary logic)
    ai_summary = f"Total reviews: {total}, Avg rating: {avg_rating:.2f}, Max rating: {max(valid_ratings) if valid_ratings else 0}, Min rating: {min(valid_ratings) if valid_ratings else 0}"

    return {
        "total_reviews": total,
        "avg_rating": round(avg_rating, 2),
        "rating_distribution": rating_distribution,
        "ai_summary": ai_summary
    }

# ---------------------------------------------------------
# Dashboard feed with competitor info
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
                "sentiment": r.sentiment,
                "competitor": r.competitor_name
            }
            for r in reviews
        ]
    }
