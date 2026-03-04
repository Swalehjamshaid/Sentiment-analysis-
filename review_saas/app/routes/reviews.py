# filename: app/routes/reviews.py
from __future__ import annotations
import logging
from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import select
from datetime import datetime
from app.core.db import get_session
from app.core.models import Review, Company
from app.services.google_reviews import fetch_place_details

router = APIRouter(tags=['reviews'])
logger = logging.getLogger(__name__)

# --- VIEW REVIEWS FOR A COMPANY ---
@router.get("/reviews")
async def get_company_reviews(company_id: int, page: int = 1, size: int = 20):
    async with get_session() as session:
        # Check company exists
        result = await session.execute(select(Company).where(Company.id == company_id))
        company = result.scalar_one_or_none()
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        # Get all reviews
        result = await session.execute(
            select(Review)
            .where(Review.company_id == company_id)
            .order_by(Review.review_time.desc())
        )
        all_reviews = result.scalars().all()
        total = len(all_reviews)
        items = all_reviews[(page-1)*size:(page-1)*size+size]

        reviews_list = [
            {
                "author": r.author_name,
                "rating": r.rating,
                "text": r.text,
                "time": r.review_time.isoformat(),
            }
            for r in items
        ]

    return {
        "success": True,
        "company": {"id": company.id, "name": company.name},
        "reviews": reviews_list,
        "total": total,
        "page": page,
        "size": size
    }

# --- FETCH GOOGLE PLACE DETAILS AND STORE IN DB ---
@router.get("/reviews/fetch_google")
async def fetch_google_place(place_id: str, company_id: int):
    """
    Fetch latest Google reviews for a place and store them in DB.
    """
    async with get_session() as session:
        # Ensure company exists
        result = await session.execute(select(Company).where(Company.id == company_id))
        company = result.scalar_one_or_none()
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        try:
            details = fetch_place_details(place_id)
        except Exception as e:
            logger.error(f"Google fetch failed: {e}")
            raise HTTPException(status_code=500, detail=f"Google fetch failed: {e}")

        reviews = details.get("reviews", [])
        if not reviews:
            return {"success": True, "message": "No new reviews found", "stored": 0}

        stored_count = 0
        for r in reviews:
            # Convert timestamp to datetime if needed
            review_time = datetime.fromtimestamp(r["time"]) if isinstance(r["time"], (int, float)) else r["time"]

            # Check if review already exists (by author + text + company)
            exists = await session.execute(
                select(Review)
                .where(
                    Review.company_id == company_id,
                    Review.author_name == r["author_name"],
                    Review.text == r["text"]
                )
            )
            if exists.scalar_one_or_none():
                continue

            new_review = Review(
                company_id=company_id,
                author_name=r["author_name"],
                rating=r.get("rating", 0),
                text=r.get("text", ""),
                review_time=review_time
            )
            session.add(new_review)
            stored_count += 1

        await session.commit()
        logger.info(f"Stored {stored_count} new reviews for company_id={company_id}")

    return {"success": True, "stored": stored_count, "total_fetched": len(reviews)}
