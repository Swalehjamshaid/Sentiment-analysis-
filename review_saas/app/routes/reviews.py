# filename: app/routes/reviews.py

from __future__ import annotations
import logging
from fastapi import APIRouter, Query, HTTPException
from sqlalchemy import select, func
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

        # 2. Get total count for pagination metadata
        count_stmt = select(func.count()).select_from(Review).where(Review.company_id == company_id)
        total_result = await session.execute(count_stmt)
        total = total_result.scalar() or 0

        # 3. Fetch paginated reviews sorted by most recent first
        # Offset calculation: (page - 1) * size
        stmt = (
            select(Review)
            .where(Review.company_id == company_id)
            .order_by(Review.google_review_time.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        result = await session.execute(stmt)
        items = result.scalars().all()

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
    async with get_session() as session:
        # 1. Verify company existence
        result = await session.execute(select(Company).where(Company.id == company_id))
        company = result.scalar_one_or_none()
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

    try:
        # 2. Trigger the sync in google_reviews.py
        # This function is now correctly imported and aligned
        await ingest_company_reviews(company_id=company_id, place_id=place_id)
        
        # 3. Get business name/address for the UI success message
        # This function is now also correctly imported
        details = await fetch_place_details(place_id)
        
        # 4. Get the updated total count from DB
        async with get_session() as session:
            count_stmt = select(func.count()).select_from(Review).where(Review.company_id == company_id)
            count_res = await session.execute(count_stmt)
            total_now = count_res.scalar() or 0

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
