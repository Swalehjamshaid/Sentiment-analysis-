# filename: app/routes/reviews.py

from __future__ import annotations
import logging
from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from datetime import datetime, timezone
from app.core.db import get_session
from app.core.models import Review, Company
# 🚨 IMPORTED ingest_company_reviews for full access
from app.services.google_reviews import fetch_place_details, ingest_company_reviews

router = APIRouter(tags=['reviews'])
logger = logging.getLogger(__name__)

@router.get("/reviews/fetch_google")
async def fetch_google_place(place_id: str, company_id: int):
    """
    Priority 1: Full Ingestion via Business API (No limit)
    Priority 2: Fallback via Places API (5 review limit)
    """
    async with get_session() as session:
        # 1. Ensure company exists
        result = await session.execute(select(Company).where(Company.id == company_id))
        company = result.scalar_one_or_none()
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

    try:
        # 2. PRIORITY: Attempt Full Ingestion (Uses GOOGLE_BUSINESS_ACCESS_TOKEN)
        # This function already contains the logic to try Business API first,
        # then fallback to Places API if the token fails.
        await ingest_company_reviews(company_id=company_id, place_id=place_id)
        
        # 3. VERIFY: Check how many reviews we now have in DB
        async with get_session() as session:
            count_res = await session.execute(
                select(Review).where(Review.company_id == company_id)
            )
            stored_reviews = count_res.scalars().all()
            
        return {
            "success": True, 
            "message": "Ingestion process completed", 
            "total_in_db": len(stored_reviews)
        }

    except Exception as e:
        logger.error(f"Ingestion failed: {e}")
        
        # 4. FINAL FALLBACK: Manual fetch if the background service crashed
        try:
            logger.info("Attempting final manual fallback via Places Details API.")
            details = fetch_place_details(place_id)
            reviews = details.get("reviews", [])
            
            # (Duplicate logic from previous version to ensure some data is saved)
            # This is limited to 5 reviews.
            async with get_session() as session:
                for r in reviews:
                    g_id = r.get("reviewId") or f"{place_id}_{r.get('time', 0)}"
                    g_time = datetime.fromtimestamp(r["time"], tz=timezone.utc) if "time" in r else datetime.now(timezone.utc)
                    
                    exists = await session.execute(select(Review).where(Review.google_review_id == g_id))
                    if exists.scalar_one_or_none(): continue
                    
                    new_review = Review(
                        company_id=company_id,
                        google_review_id=g_id,
                        author_name=r.get("author_name"),
                        rating=int(r.get("rating", 0)),
                        text=r.get("text", ""),
                        google_review_time=g_time
                    )
                    session.add(new_review)
                await session.commit()
            
            return {"success": True, "message": "Manual fallback successful", "stored": len(reviews)}
        except Exception as fallback_e:
            raise HTTPException(status_code=500, detail=f"All fetch methods failed: {fallback_e}")
