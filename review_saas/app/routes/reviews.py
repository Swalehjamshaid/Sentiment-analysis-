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
from sqlalchemy import select, desc
from pydantic import BaseModel, ConfigDict

from app.core.db import get_session
from app.core.models import Company, Review
from app.services.review import ingest_outscraper_reviews

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/reviews", tags=["reviews"])

# --------------------------- Pydantic Schema ---------------------------
class ReviewSchema(BaseModel):
    """Matches your SQLAlchemy Review model exactly with analysis fields"""
    id: int
    company_id: int
    google_review_id: str
    author_name: Optional[str] = None
    rating: Optional[int] = None
    text: Optional[str] = None
    google_review_time: Optional[datetime] = None
    sentiment_score: Optional[float] = 0.0  # Used for dashboard charts
    
    model_config = ConfigDict(from_attributes=True)

# --------------------------- Streaming Helper ---------------------------
async def review_streamer(company_id: int, start: date, end: date, limit: int, session: AsyncSession):
    """
    Query the database and yield reviews one-by-one as SSE events.
    """
    # Sort by time descending so the dashboard shows newest data first
    query = select(Review).where(Review.company_id == company_id).order_by(desc(Review.google_review_time))
    
    if start:
        query = query.where(Review.google_review_time >= start)
    if end:
        query = query.where(Review.google_review_time <= end)
    
    result = await session.execute(query.limit(limit))
    reviews = result.scalars().all()

    for i, review in enumerate(reviews):
        # Validate through Pydantic to ensure JSON compatibility
        review_data = ReviewSchema.model_validate(review).model_dump_json()
        
        # Format as Server-Sent Event (SSE)
        yield f"event: review\ndata: {review_data}\n\n"
        
        # Artificial delay to prevent UI flickering and allow smooth animation
        await asyncio.sleep(0.05)

    # Signal to the frontend that the stream is finished
    yield "event: done\ndata: {\"status\": \"completed\"}\n\n"

# --------------------------- Fetch Reviews API ---------------------------
@router.get("/", response_model=List[ReviewSchema])
async def get_reviews(
    company_id: int = Query(...),
    start: Optional[date] = Query(None),
    end: Optional[date] = Query(None),
    limit: int = Query(50),
    session: AsyncSession = Depends(get_session),
):
    """Standard REST endpoint for fetching a static list of reviews"""
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
    limit: int = Query(250),
    session: AsyncSession = Depends(get_session),
):
    """
    SSE Endpoint for incremental dashboard updates. 
    Use this to 'pop' reviews into the UI one by one.
    """
    return StreamingResponse(
        review_streamer(company_id, start, end, limit, session),
        media_type="text/event-stream"
    )

# --------------------------- Ingest Reviews API ---------------------------
@router.post("/ingest/{company_id}")
async def ingest_reviews(
    company_id: int,
    max_reviews: int = Query(200),
    session: AsyncSession = Depends(get_session),
):
    """Trigger the Outscraper service to pull fresh data from Google Maps"""
    result = await session.execute(select(Company).where(Company.id == company_id))
    company = result.scalars().first()
    
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    try:
        new_count = await ingest_outscraper_reviews(company, session, max_reviews=max_reviews)
        return {
            "status": "success",
            "message": f"✅ Stored {new_count} new reviews for {company.name}",
            "company_id": company_id
        }
    except Exception as e:
        logger.error(f"Ingestion failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to ingest reviews from provider.")
