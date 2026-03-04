# filename: app/routes/reviews.py
from __future__ import annotations
from fastapi import APIRouter, Request, Query
from fastapi.responses import JSONResponse
from sqlalchemy import select
from app.core.db import get_session
from app.core.models import Review, Company
from app.services.google_reviews import ingest_company_reviews, fetch_place_details

router = APIRouter(tags=['reviews'])


# --- VIEW REVIEWS FOR A COMPANY ---
@router.get("/reviews")
async def get_company_reviews(company_id: int, page: int = 1, size: int = 20):
    """
    Returns reviews from the database for a given company.
    """
    async with get_session() as session:
        result = await session.execute(select(Company).where(Company.id == company_id))
        company = result.scalar_one_or_none()
        if not company:
            return JSONResponse(status_code=404, content={"success": False, "message": "Company not found"})

        result = await session.execute(
            select(Review)
            .where(Review.company_id == company_id)
            .order_by(Review.review_date.desc())
        )
        all_reviews = result.scalars().all()
        total = len(all_reviews)
        items = all_reviews[(page-1)*size:(page-1)*size+size]

        reviews_list = [
            {
                "author": r.author_name,
                "rating": r.rating,
                "text": r.text,
                "time": r.review_date,
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


# --- FETCH AND STORE GOOGLE REVIEWS ---
@router.post("/reviews/fetch_google")
async def fetch_and_store_google_reviews(company_id: int, place_id: str):
    """
    Fetches latest reviews from Google API and saves them to the database.
    """
    try:
        # Ingest reviews into the database
        await ingest_company_reviews(company_id, place_id)

        # Return updated list of reviews from DB
        async with get_session() as session:
            result = await session.execute(
                select(Review)
                .where(Review.company_id == company_id)
                .order_by(Review.review_date.desc())
            )
            all_reviews = result.scalars().all()

            reviews_list = [
                {
                    "author": r.author_name,
                    "rating": r.rating,
                    "text": r.text,
                    "time": r.review_date,
                }
                for r in all_reviews
            ]

        return {"success": True, "reviews": reviews_list, "total": len(all_reviews)}

    except Exception as e:
        return {"success": False, "message": str(e)}


# --- FETCH LATEST GOOGLE PLACE DETAILS ---
@router.get("/reviews/google_details")
async def fetch_google_place_details(place_id: str):
    """
    Fetches latest Google Place details (rating, name, address) without storing in DB.
    """
    try:
        details = fetch_place_details(place_id)
        return {"success": True, "details": details}
    except Exception as e:
        return {"success": False, "message": str(e)}
