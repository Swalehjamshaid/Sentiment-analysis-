# filename: app/routes/reviews.py

from __future__ import annotations
import logging
from fastapi import APIRouter, Query, HTTPException
from sqlalchemy import select
from datetime import datetime, timezone
from app.core.db import get_session
from app.core.models import Review, Company
# 🚨 UPDATED: Import ingest_company_reviews to use the new centralized async logic
from app.services.google_reviews import fetch_place_details, ingest_company_reviews

router = APIRouter(tags=['reviews'])
logger = logging.getLogger(__name__)

# --- VIEW REVIEWS FOR A COMPANY ---
@router.get("/reviews")
async def get_company_reviews(company_id: int, page: int = 1, size: int = 20):
    async with get_session() as session:
        result = await session.execute(select(Company).where(Company.id == company_id))
        company = result.scalar_one_or_none()
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        # Get all reviews using the correct model field: google_review_time
        result = await session.execute(
            select(Review)
            .where(Review.company_id == company_id)
            .order_by(Review.google_review_time.desc())
        )
        all_reviews = result.scalars().all()
        total = len(all_reviews)
        items = all_reviews[(page-1)*size : (page-1)*size+size]

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

# --- FETCH GOOGLE PLACE DETAILS AND STORE IN DB ---
@router.get("/reviews/fetch_google")
async def fetch_google_place(place_id: str, company_id: int):
    """
    Triggers the strict Business API ingestion from google_reviews.py
    """
    async with get_session() as session:
        # Ensure company exists
        result = await session.execute(select(Company).where(Company.id == company_id))
        company = result.scalar_one_or_none()
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

    try:
        # 🚨 FIXED: Now calling the service function with 'await'
        # This handles the GOOGLE_BUSINESS_ACCESS_TOKEN logic and DB saving automatically
        await ingest_company_reviews(company_id=company_id, place_id=place_id)
        
        # 🚨 FIXED: Now 'awaiting' the async details fetch
        details = await fetch_place_details(place_id)
        
        # Get the new total count from DB for the response
        async with get_session() as session:
            count_res = await session.execute(
                select(Review).where(Review.company_id == company_id)
            )
            total_now = len(count_res.scalars().all())

        return {
            "success": True, 
            "message": "Full history ingestion triggered via Business API",
            "company_name": details.get("name"),
            "total_reviews_in_db": total_now
        }

    except Exception as e:
        logger.error(f"Google fetch/ingest failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
