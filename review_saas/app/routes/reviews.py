# filename: app/routes/reviews.py

from __future__ import annotations
import logging
from fastapi import APIRouter, Query, HTTPException
from sqlalchemy import select
from datetime import datetime, timezone
from app.core.db import get_session
from app.core.models import Review, Company
from app.services.google_reviews import fetch_place_details, ingest_company_reviews

# ✅ REQUIRED: This line fixes your 'NameError'
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

        # Sorting by the correct model attribute
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

# --- FETCH FULL HISTORY VIA BUSINESS API ---
@router.get("/reviews/fetch_google")
async def fetch_google_place(place_id: str, company_id: int):
    async with get_session() as session:
        result = await session.execute(select(Company).where(Company.id == company_id))
        company = result.scalar_one_or_none()
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

    try:
        # 1. Trigger Full Ingestion (Strict Business API)
        await ingest_company_reviews(company_id=company_id, place_id=place_id)
        
        # 2. Fetch basic details for the response
        details = await fetch_place_details(place_id)
        
        # 3. Get updated count from Postgres
        async with get_session() as session:
            count_res = await session.execute(
                select(Review).where(Review.company_id == company_id)
            )
            total_now = len(count_res.scalars().all())

        return {
            "success": True, 
            "message": "Full history fetched via Google Business API",
            "company_name": details.get("name") if details else company.name,
            "total_reviews_in_db": total_now
        }

    except Exception as e:
        logger.error(f"Sync failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
