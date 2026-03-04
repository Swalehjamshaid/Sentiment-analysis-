# filename: app/routes/reviews.py
from __future__ import annotations
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from app.core.db import get_session
from app.core.models import Review, Company
from app.services.google_reviews import fetch_place_details
from datetime import datetime
import logging

logger = logging.getLogger("reviews")
router = APIRouter(tags=["reviews"])

# --- VIEW REVIEWS FOR A COMPANY ---
@router.get("/reviews")
async def get_company_reviews(
    company_id: int,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1),
):
    async with get_session() as session:
        result = await session.execute(select(Company).where(Company.id == company_id))
        company = result.scalar_one_or_none()
        if not company:
            return JSONResponse(status_code=404, content={"success": False, "message": "Company not found"})

        result = await session.execute(
            select(Review)
            .where(Review.company_id == company_id)
            .order_by(Review.review_time.desc())
        )
        all_reviews = result.scalars().all()
        total = len(all_reviews)
        items = all_reviews[(page - 1) * size : (page - 1) * size + size]

        reviews_list = [
            {"author": r.author_name, "rating": r.rating, "text": r.text, "time": r.review_time}
            for r in items
        ]

    return {"success": True, "company": {"id": company.id, "name": company.name}, "reviews": reviews_list, "total": total, "page": page, "size": size}


# --- FETCH GOOGLE PLACE DETAILS AND SAVE TO DB ---
@router.get("/reviews/fetch_google")
async def fetch_google_place(place_id: str, company_id: int):
    async with get_session() as session:
        try:
            # Get company
            result = await session.execute(select(Company).where(Company.id == company_id))
            company = result.scalar_one_or_none()
            if not company:
                return JSONResponse(status_code=404, content={"success": False, "message": "Company not found"})

            # Fetch Google reviews
            details = fetch_place_details(place_id)
            reviews = details.get("reviews", [])
            logger.info(f"Fetched {len(reviews)} reviews from Google for company {company.name}")

            saved_count = 0
            for r in reviews:
                # Convert timestamp to datetime if needed
                review_time = r.get("time")
                if isinstance(review_time, (int, float)):
                    review_time = datetime.utcfromtimestamp(review_time)

                # Check if review already exists
                existing = await session.execute(
                    select(Review).where(
                        Review.company_id == company.id,
                        Review.author_name == r.get("author_name"),
                        Review.review_time == review_time,
                    )
                )
                if existing.scalar_one_or_none():
                    continue  # Skip duplicate

                review = Review(
                    company_id=company.id,
                    author_name=r.get("author_name"),
                    rating=r.get("rating"),
                    text=r.get("text"),
                    review_time=review_time or datetime.utcnow(),
                )
                session.add(review)
                saved_count += 1

            await session.commit()
            logger.info(f"Saved {saved_count} new reviews for company {company.name}")

            return {"success": True, "fetched_reviews": len(reviews), "saved_reviews": saved_count}

        except SQLAlchemyError as e:
            await session.rollback()
            logger.error(f"DB error: {str(e)}")
            return {"success": False, "message": f"Database error: {str(e)}"}
        except Exception as e:
            logger.error(f"Google API error: {str(e)}")
            return {"success": False, "message": f"Google API error: {str(e)}"}
