from __future__ import annotations
import logging
import re
from datetime import datetime
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from pydantic import BaseModel

from app.core.db import get_session
from app.core.models import Review, Company
from app.services.scraper import fetch_reviews

router = APIRouter()
logger = logging.getLogger(__name__)

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
@router.post("/ingest/{company_id}")
async def ingest_reviews(company_id: int, session: AsyncSession = Depends(get_session)):
    """
    Triggers the Playwright scraper using the correct Google identifiers 
    defined in models.py and saves them to the database.
    """
    # 1. Fetch Company from DB
    result = await session.execute(select(Company).where(Company.id == company_id))
    company = result.scalar_one_or_none()
    
    if not company:
        raise HTTPException(status_code=404, detail="Company record not found in database.")

    # 2. Correct Identifier Mapping (Crucial Fix for 500 Error)
    # Your models.py uses 'google_place_id' or 'place_url'
    target_id = company.google_place_id or company.place_url
    
    if not target_id:
        logger.error(f"Company ID {company_id} is missing both google_place_id and place_url.")
        raise HTTPException(
            status_code=400, 
            detail="Business is missing a valid Google Place ID or URL to start scraping."
        )

    try:
        logger.info(f"🚀 Starting Playwright scraper for: {company.name}")

        # 3. Call the Scraper Service
        # We pass the target_id (Place ID or URL) and limit to 300
        scraped_data = await fetch_reviews(place_id=target_id, limit=300)
        
        if not scraped_data:
            logger.warning(f"⚠️ Scraper returned 0 results for {company.name}. Check Google Maps layout.")
            return {"status": "success", "message": "No reviews found on page.", "count": 0}

        # 4. Persistence with Duplicate Prevention
        new_count = 0
        for item in scraped_data:
            # Check if this specific Google Review ID already exists for this company
            # Matches the UniqueConstraint in your models.py
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
                    google_review_id=item["review_id"], # Map scraper 'review_id' to model 'google_review_id'
                    author_name=item.get("author_name", "Anonymous"),
                    rating=item.get("rating", 0),
                    text=item.get("text", ""),
                    source_platform="Google",
                    first_seen_at=datetime.utcnow()
                )
                session.add(new_review)
                new_count += 1

        # 5. Commit Transaction
        await session.commit()
        logger.info(f"✅ Ingested {new_count} new reviews for {company.name}.")

        return {
            "status": "success",
            "company_name": company.name,
            "new_reviews_added": new_count,
            "total_fetched": len(scraped_data)
        }

    except Exception as e:
        await session.rollback()
        logger.error(f"❌ Critical Failure during ingestion: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500, 
            detail=f"Internal Scraper Crash: {str(e)}"
        )

# --------------------------- List Reviews (GET) ---------------------------
@router.get("/", response_model=List[ReviewResponse])
async def list_reviews(
    company_id: Optional[int] = Query(None),
    session: AsyncSession = Depends(get_session)
):
    """
    Retrieves stored reviews, optionally filtered by company_id.
    """
    try:
        query = select(Review)
        if company_id:
            query = query.where(Review.company_id == company_id)
        
        result = await session.execute(query.order_by(Review.id.desc()))
        return result.scalars().all()
    except Exception as e:
        logger.error(f"Error fetching reviews: {str(e)}")
        raise HTTPException(status_code=500, detail="Could not retrieve reviews from database.")

# --------------------------- Delete Review (DELETE) ---------------------------
@router.delete("/{review_id}")
async def delete_review(review_id: int, session: AsyncSession = Depends(get_session)):
    """
    Deletes a specific review record by its internal database ID.
    """
    try:
        await session.execute(delete(Review).where(Review.id == review_id))
        await session.commit()
        return {"status": "success", "message": f"Review {review_id} deleted."}
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=500, detail=str(e))
