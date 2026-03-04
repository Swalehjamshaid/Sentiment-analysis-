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

router = APIRouter(tags=['reviews'])

# --- VIEW REVIEWS FOR A COMPANY ---
@router.get("/reviews")
async def get_company_reviews(
    company_id: int,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1)
):
    async with get_session() as session:
        # Get company
        result = await session.execute(select(Company).where(Company.id == company_id))
        company = result.scalar_one_or_none()
        if not company:
            return JSONResponse(status_code=404, content={"success": False, "message": "Company not found"})

        # Get reviews for the company
        result = await session.execute(
            select(Review)
            .where(Review.company_id == company_id)
            .order_by(Review.review_time.desc())
        )
        all_reviews = result.scalars().all()
        total = len(all_reviews)
        items = all_reviews[(page - 1) * size : (page - 1) * size + size]

        reviews_list = [
            {
                "author": r.author_name,
                "rating": r.rating,
                "text": r.text,
                "time": r.review_time,
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

# --- FETCH LATEST GOOGLE PLACE DETAILS AND STORE IN DB ---
@router.get("/reviews/fetch_google")
async def fetch_google_place(place_id: str, company_id: int):
    async with get_session() as session:
        try:
            # Get company
            result = await session.execute(select(Company).where(Company.id == company_id))
            company = result.scalar_one_or_none()
            if not company:
                return JSONResponse(status_code=404, content={"success": False, "message": "Company not found"})

            # Fetch Google place details
            details = fetch_place_details(place_id)
            reviews = details.get("reviews", [])

            # Save new reviews to DB
            for r in reviews:
                existing = await session.execute(
                    select(Review).where(
                        Review.company_id == company.id,
                        Review.author_name == r.get("author_name"),
                        Review.review_time == r.get("time")
                    )
                )
                if existing.scalar_one_or_none():
                    continue  # Skip if review already exists

                review = Review(
                    company_id=company.id,
                    author_name=r.get("author_name"),
                    rating=r.get("rating"),
                    text=r.get("text"),
                    review_time=r.get("time") or datetime.utcnow()
                )
                session.add(review)

            await session.commit()

            return {"success": True, "fetched_reviews": len(reviews)}

        except SQLAlchemyError as e:
            await session.rollback()
            return {"success": False, "message": f"Database error: {str(e)}"}
        except Exception as e:
            return {"success": False, "message": f"Google API error: {str(e)}"}
