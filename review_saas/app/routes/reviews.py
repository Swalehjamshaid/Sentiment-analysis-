# filename: app/routes/reviews.py

from __future__ import annotations
import logging
import json
import asyncio
from typing import Optional, List
from datetime import datetime, date

from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func
from pydantic import BaseModel, ConfigDict

from app.core.db import get_session
from app.core.models import Company, Review
from app.services.review import ingest_outscraper_reviews

logger = logging.getLogger(__name__)

# Fixed pathing for Railway deployments
router = APIRouter(prefix="/api/reviews", tags=["reviews"], redirect_slashes=False)

# --------------------------- Pydantic Schema ---------------------------
class ReviewSchema(BaseModel):
    """Full Review model for deep analysis"""
    id: int
    company_id: int
    google_review_id: str
    author_name: Optional[str] = None
    rating: Optional[int] = None
    text: Optional[str] = None
    google_review_time: Optional[datetime] = None
    sentiment_score: Optional[float] = 0.0
    
    model_config = ConfigDict(from_attributes=True)

# --------------------------- Streaming Helper ---------------------------
async def review_streamer(company_id: int, start: Optional[date], end: Optional[date], limit: int, session: AsyncSession):
    """
    Streams the complete database content for real-time dashboard population.
    """
    query = select(Review).where(Review.company_id == company_id).order_by(desc(Review.google_review_time))
    
    if start:
        query = query.where(Review.google_review_time >= start)
    if end:
        query = query.where(Review.google_review_time <= end)
    
    result = await session.execute(query.limit(limit))
    reviews = result.scalars().all()

    for review in reviews:
        review_data = ReviewSchema.model_validate(review).model_dump_json()
        yield f"event: review\ndata: {review_data}\n\n"
        await asyncio.sleep(0.005) # Increased speed for high-volume analysis

    yield "event: done\ndata: completed\n\n"

# --------------------------- Fetch Reviews API ---------------------------
@router.get("", response_model=List[ReviewSchema])
async def get_reviews(
    company_id: int = Query(...),
    start: Optional[date] = Query(None),
    end: Optional[date] = Query(None),
    # Set to a massive limit to ensure 100% of the database is captured for analysis
    limit: int = Query(50000), 
    session: AsyncSession = Depends(get_session),
):
    """
    Returns the complete interaction history for a company. 
    Use this to calculate full-scale KPIs and Trends.
    """
    query = select(Review).where(Review.company_id == company_id).order_by(desc(Review.google_review_time))
    
    if start:
        query = query.where(Review.google_review_time >= start)
    if end:
        query = query.where(Review.google_review_time <= end)
    
    result = await session.execute(query.limit(limit))
    return result.scalars().all()

# --------------------------- Streaming API ---------------------------
@router.get("/stream")
async def stream_reviews(
    company_id: int = Query(...),
    start: Optional[date] = Query(None),
    end: Optional[date] = Query(None),
    limit: int = Query(50000), 
    session: AsyncSession = Depends(get_session),
):
    """
    SSE Endpoint to sync the frontend with the entire database content.
    """
    return StreamingResponse(
        review_streamer(company_id, start, end, limit, session),
        media_type="text/event-stream"
    )

# --------------------------- Ingest Reviews API ---------------------------
@router.post("/ingest/{company_id}")
async def ingest_reviews(
    company_id: int,
    max_reviews: int = Query(500), # Increased ingestion ceiling
    session: AsyncSession = Depends(get_session),
):
    """
    Triggers Outscraper and returns the fresh sync count.
    """
    result = await session.execute(select(Company).where(Company.id == company_id))
    company = result.scalars().first()
    
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    try:
        # result should return a dict with 'new_count' and 'total_fetched' 
        # for proper dashboard tracking.
        new_count = await ingest_outscraper_reviews(company, session, max_reviews=max_reviews)
        
        # Verify total database count after ingestion
        count_query = select(func.count()).select_from(Review).where(Review.company_id == company_id)
        total_res = await session.execute(count_query)
        total_in_db = total_res.scalar()

        return {
            "status": "success",
            "message": f"Sync complete. Found {new_count} new items.",
            "total_database_count": total_in_db
        }
    except Exception as e:
        logger.error(f"Ingestion Error: {str(e)}")
        raise HTTPException(status_code=500, detail="Service sync failed.")
