from __future__ import annotations
import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from pydantic import BaseModel

# Core project imports
from app.core.db import get_session
from app.core.models import Review, Company
from app.services.scraper import fetch_reviews   # Updated scraper

router = APIRouter(tags=["reviews"])
logger = logging.getLogger("app.reviews")


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


@router.post("/reviews/ingest/{company_id}")
async def ingest_reviews(
    company_id: int,
    session: AsyncSession = Depends(get_session)
):
    """Ingest Google reviews for a company - uses CID from database only"""

    # 1. Fetch Company
    result = await session.execute(
        select(Company).where(Company.id == company_id)
    )
    company = result.scalar_one_or_none()
   
    if not company:
        raise HTTPException(status_code=404, detail="Company not found.")

    target_name = str(company.name)
    target_place_id = company.google_place_id  # Keeping for potential future use

    try:
        logger.info(f"🚀 Starting Ingest for: {target_name} (Company ID: {company_id})")

        # 2. Fetch reviews from scraper (no company_id or session passed)
        scraped_data = await fetch_reviews(
            place_id=target_place_id,
            name=target_name,
            limit=300
        )
       
        if not scraped_data:
            logger.info(f"ℹ️ No reviews returned for {target_name}")
            return {
                "status": "success", 
                "message": "No reviews found or CID not available in database.", 
                "new_reviews_added": 0
            }

        # 3. Save new reviews only (avoid duplicates)
        new_count = 0
        for item in scraped_data:
            # Check if review already exists
            check = await session.execute(
                select(Review).where(
                    Review.company_id == company_id,
                    Review.google_review_id == item.get("review_id")
                )
            )
            
            if not check.scalar_one_or_none():
                new_review = Review(
                    company_id=company_id,
                    google_review_id=item.get("review_id"),
                    author_name=item.get("author_name", "Anonymous"),
                    rating=item.get("rating", 0),
                    text=item.get("text", ""),
                    source_platform="Google",
                    first_seen_at=datetime.utcnow()
                )
                session.add(new_review)
                new_count += 1

        await session.commit()

        logger.info(f"✅ Ingest completed for {target_name}: {new_count} new reviews added.")
        
        return {
            "status": "success", 
            "company_name": target_name, 
            "new_reviews_added": new_count,
            "total_scraped": len(scraped_data)
        }

    except Exception as e:
        await session.rollback()
        logger.error(f"❌ Ingest error for company {company_id} ({target_name}): {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/reviews", response_model=List[ReviewResponse])
async def list_reviews(
    company_id: Optional[int] = Query(None),
    session: AsyncSession = Depends(get_session)
):
    """List reviews, optionally filtered by company"""
    query = select(Review)
    if company_id:
        query = query.where(Review.company_id == company_id)
    
    result = await session.execute(query.order_by(Review.id.desc()))
    return result.scalars().all()


@router.delete("/reviews/{review_id}")
async def delete_review(review_id: int, session: AsyncSession = Depends(get_session)):
    """Delete a specific review"""
    await session.execute(delete(Review).where(Review.id == review_id))
    await session.commit()
    return {"status": "success", "message": "Review deleted."}
