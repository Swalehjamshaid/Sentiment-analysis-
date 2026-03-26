from __future__ import annotations
import logging
import re
from datetime import datetime
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from pydantic import BaseModel

# Core project imports
from app.core.db import get_session
from app.core.models import Review, Company
from app.services.scraper import fetch_reviews

# No prefix here because app/main.py handles prefix="/api"
router = APIRouter(tags=["reviews"])
logger = logging.getLogger("app.reviews")

# --------------------------- Pydantic Schemas ---------------------------
class ReviewResponse(BaseModel):
    id: int
    company_id: int
    google_review_id: str
    author_name: Optional[str] = None
    rating: Optional[int] = 0
    text: Optional[str] = None
    google_review_time: Optional[datetime] = None

    class Config:
        from_attributes = True

# --------------------------- Ingest Reviews (POST) ---------------------------
@router.post("/reviews/ingest/{company_id}")
async def ingest_reviews(
    company_id: int, 
    session: AsyncSession = Depends(get_session)
):
    """
    Triggers the Playwright scraper and saves results to the database.
    Fixed to avoid MissingGreenlet errors by caching attributes locally.
    """
    # 1. Fetch Company from DB
    result = await session.execute(select(Company).where(Company.id == company_id))
    company = result.scalar_one_or_none()
    
    if not company:
        logger.error(f"Sync failed: Company ID {company_id} not found.")
        raise HTTPException(status_code=404, detail="Company record not found.")

    # CRITICAL FIX: Save these to local variables immediately. 
    # Do not access 'company.x' inside the 'except' block or after the scraper call.
    target_name = str(company.name)
    target_id = company.google_place_id or getattr(company, 'place_url', None)
    
    if not target_id:
        logger.error(f"Company {target_name} is missing Google Place ID/URL.")
        raise HTTPException(
            status_code=400, 
            detail="Business is missing a valid Google Place ID or URL."
        )

    try:
        logger.info(f"🚀 Starting Playwright scraper for: {target_name}")

        # 2. Call the Scraper Service (Aligned with scraper.py keys)
        scraped_data = await fetch_reviews(place_id=target_id, limit=300)
        
        if not scraped_data:
            logger.warning(f"⚠️ 0 results for {target_name}.")
            return {
                "status": "success", 
                "message": "Sync complete. No reviews found.", 
                "new_reviews_added": 0
            }

        # 3. Persistence with Duplicate Prevention
        new_count = 0
        for item in scraped_data:
            # Check for duplicates using the unique Google Review ID
            check_query = await session.execute(
                select(Review).where(
                    Review.company_id == company_id,
                    Review.google_review_id == item["review_id"]
                )
            )
            existing_review = check_query.scalar_one_or_none()

            if not existing_review:
                new_review = Review(
                    company_id=company_id,
                    google_review_id=item["review_id"],
                    author_name=item.get("author_name", "Anonymous"),
                    rating=item.get("rating", 0),
                    text=item.get("text", ""),
                    source_platform="Google",
                    first_seen_at=datetime.utcnow()
                )
                session.add(new_review)
                new_count += 1

        # 4. Commit Transaction
        await session.commit()
        logger.info(f"✅ Ingested {new_count} new reviews for {target_name}.")

        return {
            "status": "success",
            "company_name": target_name,
            "new_reviews_added": new_count,
            "total_fetched": len(scraped_data)
        }

    except Exception as e:
        await session.rollback()
        # Using target_name here prevents the MissingGreenlet crash
        logger.error(f"❌ Failure for {target_name}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500, 
            detail=f"Internal Scraper Crash: {str(e)}"
        )

# --------------------------- List Reviews (GET) ---------------------------
@router.get("/reviews", response_model=List[ReviewResponse])
async def list_reviews(
    company_id: Optional[int] = Query(None),
    session: AsyncSession = Depends(get_session)
):
    try:
        query = select(Review)
        if company_id:
            query = query.where(Review.company_id == company_id)
        
        result = await session.execute(query.order_by(Review.id.desc()))
        return result.scalars().all()
    except Exception as e:
        logger.error(f"Error fetching reviews: {str(e)}")
        raise HTTPException(status_code=500, detail="Could not retrieve reviews.")

# --------------------------- Delete Review (DELETE) ---------------------------
@router.delete("/reviews/{review_id}")
async def delete_review(review_id: int, session: AsyncSession = Depends(get_session)):
    try:
        await session.execute(delete(Review).where(Review.id == review_id))
        await session.commit()
        return {"status": "success", "message": f"Review {review_id} deleted."}
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=500, detail=str(e))
