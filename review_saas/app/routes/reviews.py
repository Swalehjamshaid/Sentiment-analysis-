# filename: app/routes/reviews.py

from __future__ import annotations
import logging
from fastapi import APIRouter, Query, HTTPException
from sqlalchemy import select
from app.core.db import get_session
from app.core.models import Review, Company
from app.services.google_reviews import fetch_place_details, ingest_company_reviews

# ✅ Router initialization
router = APIRouter(tags=['reviews'])
logger = logging.getLogger(__name__)

# --- VIEW REVIEWS FOR A COMPANY ---
@router.get("/reviews")
async def get_company_reviews(company_id: int, page: int = 1, size: int = 20):
    """
    Retrieves stored reviews for a specific company from Postgres.
    Pagination and sorting aligned with the Review model.
    """
    async with get_session() as session:
        # 1. Verify the company exists
        result = await session.execute(select(Company).where(Company.id == company_id))
        company = result.scalar_one_or_none()
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        # 2. Fetch reviews sorted by most recent first
        # Uses 'google_review_time' from app/core/models.py
        result = await session.execute(
            select(Review)
            .where(Review.company_id == company_id)
            .order_by(Review.google_review_time.desc())
        )
        all_reviews = result.scalars().all()
        total = len(all_reviews)
        
        # 3. Apply manual pagination
        items = all_reviews[(page-1)*size : (page-1)*size+size]

        # 4. Map to clean JSON response
        reviews_list = [
            {
                "author": r.author_name,
                "rating": r.rating,
                "text": r.text,
                "time": r.google_review_time.isoformat() if r.google_review_time else None,
                "photo": r.profile_photo_url
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

# --- FETCH DATA FROM GOOGLE ---
@router.get("/reviews/fetch_google")
async def fetch_google_place(place_id: str, company_id: int):
    """
    Triggers the ingestion service. 
    Matches the button click on the Dashboard.
    """
    # Verify company existence first
    async with get_session() as session:
        result = await session.execute(select(Company).where(Company.id == company_id))
        company = result.scalar_one_or_none()
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

    try:
        # 1. Trigger the sync in google_reviews.py
        await ingest_company_reviews(company_id=company_id, place_id=place_id)
        
        # 2. Get business name/address for the UI success message
        details = await fetch_place_details(place_id)
        
        # 3. Get the new total count to show in the UI response
        async with get_session() as session:
            count_res = await session.execute(
                select(Review).where(Review.company_id == company_id)
            )
            total_now = len(count_res.scalars().all())

        return {
            "success": True, 
            "message": "Sync complete using Google API Key",
            "company_name": details.get("name") if details else company.name,
            "total_reviews_in_db": total_now
        }

    except Exception as e:
        logger.error(f"Sync process failed: {e}")
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to fetch data from Google: {str(e)}"
        )
