# filename: app/routes/reviews.py

from __future__ import annotations
import logging
from fastapi import APIRouter, Query, HTTPException
from sqlalchemy import select
from datetime import datetime, timezone
from app.core.db import get_session
from app.core.models import Review, Company
from app.services.google_reviews import fetch_place_details, ingest_company_reviews

# ✅ Initialize the router to prevent NameError
router = APIRouter(tags=['reviews'])
logger = logging.getLogger(__name__)

# --- VIEW REVIEWS FOR A COMPANY ---
@router.get("/reviews")
async def get_company_reviews(company_id: int, page: int = 1, size: int = 20):
    """
    Retrieves stored reviews for a specific company from Postgres.
    Aligned with google_review_time and author_name fields.
    """
    async with get_session() as session:
        # Verify the company exists
        result = await session.execute(select(Company).where(Company.id == company_id))
        company = result.scalar_one_or_none()
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        # Sort by the model-aligned timestamp field: google_review_time
        result = await session.execute(
            select(Review)
            .where(Review.company_id == company_id)
            .order_by(Review.google_review_time.desc())
        )
        all_reviews = result.scalars().all()
        total = len(all_reviews)
        
        # Implement basic pagination
        items = all_reviews[(page-1)*size : (page-1)*size+size]

        # Map to JSON response using correct model attributes
        reviews_list = [
            {
                "author": r.author_name,
                "rating": r.rating,
                "text": r.text,
                "time": r.google_review_time.isoformat() if r.google_review_time else None,
                "photo": r.profile_photo_url,
                "language": r.language
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

# --- FETCH FULL HISTORY VIA BUSINESS API ---
@router.get("/reviews/fetch_google")
async def fetch_google_place(place_id: str, company_id: int):
    """
    Triggers the ingest_company_reviews service to fetch full history 
    via Google Business API using the OAuth token.
    """
    async with get_session() as session:
        # Check company exists before starting ingestion
        result = await session.execute(select(Company).where(Company.id == company_id))
        company = result.scalar_one_or_none()
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

    try:
        # 1. Trigger Full Ingestion (Strict Business API path)
        # This function handles unique ID generation and transaction commits
        await ingest_company_reviews(company_id=company_id, place_id=place_id)
        
        # 2. Fetch basic details for the response metadata
        # Restored as an async function in the service file
        details = await fetch_place_details(place_id)
        
        # 3. Get the final updated count from Postgres
        async with get_session() as session:
            count_res = await session.execute(
                select(Review).where(Review.company_id == company_id)
            )
            total_now = len(count_res.scalars().all())

        return {
            "success": True, 
            "message": "Full history fetched and synced via Google Business API",
            "company_name": details.get("name") if details else company.name,
            "total_reviews_in_db": total_now
        }

    except Exception as e:
        logger.error(f"Sync process failed: {e}")
        # Return the error details to help with troubleshooting tokens/permissions
        raise HTTPException(status_code=500, detail=f"Google Sync Failed: {str(e)}")
