# File: review_saas/app/routes/reviews.py
from __future__ import annotations
import logging
from fastapi import APIRouter, HTTPException
from sqlalchemy import select, func
from app.core.db import get_session
from app.core.models import Review, Company
from app.services.google_reviews import fetch_place_details, ingest_company_reviews

router = APIRouter(tags=['reviews'])
logger = logging.getLogger(__name__)

@router.get("/reviews")
async def get_company_reviews(company_id: int, page: int = 1, size: int = 20):
    async with get_session() as session:
        # 1. Verify Company
        result = await session.execute(select(Company).where(Company.id == company_id))
        company = result.scalar_one_or_none()
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        # 2. Count Total
        count_stmt = select(func.count()).select_from(Review).where(Review.company_id == company_id)
        total_res = await session.execute(count_stmt)
        total = total_res.scalar() or 0

        # 3. Paginated Results
        stmt = (
            select(Review)
            .where(Review.company_id == company_id)
            .order_by(Review.google_review_time.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        items_res = await session.execute(stmt)
        items = items_res.scalars().all()

        return {
            "success": True,
            "reviews": [
                {
                    "author": r.author_name,
                    "rating": r.rating,
                    "text": r.text,
                    "time": r.google_review_time.isoformat() if r.google_review_time else None,
                    "photo": r.profile_photo_url
                } for r in items
            ],
            "total": total,
            "page": page,
            "size": size
        }

@router.get("/reviews/fetch_google")
async def fetch_google_place(place_id: str, company_id: int):
    """Matches the 'Fetch Data' button on the dashboard."""
    try:
        # 1. Trigger the Outscraper Sync
        await ingest_company_reviews(place_id=place_id, company_id=company_id)
        
        # 2. Fetch place name for UI (Optional)
        details = await fetch_place_details(place_id)
        
        # 3. Get updated count from DB
        async with get_session() as session:
            count_stmt = select(func.count()).select_from(Review).where(Review.company_id == company_id)
            count_res = await session.execute(count_stmt)
            total_now = count_res.scalar() or 0

        return {
            "success": True, 
            "message": f"Sync complete via Outscraper. Total reviews: {total_now}",
            "total_reviews_in_db": total_now
        }

    except Exception as e:
        logger.error(f"Sync failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
