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

# CRITICAL FIX: redirect_slashes=False stops the 307 Temporary Redirect loop on Railway
router = APIRouter(prefix="/api/reviews", tags=["reviews"], redirect_slashes=False)

# --------------------------- Pydantic Schema ---------------------------
class ReviewSchema(BaseModel):
    """Matches the SQLAlchemy Review model exactly for JSON serialization"""
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
    Query the database and yield reviews one-by-one as SSE events.
    Order by time descending to show newest first.
    """
    # Fetch all reviews for the specific company
    query = select(Review).where(Review.company_id == company_id).order_by(desc(Review.google_review_time))
    
    if start:
        query = query.where(Review.google_review_time >= start)
    if end:
        query = query.where(Review.google_review_time <= end)
    
    # Use the high limit to ensure no data is truncated
    result = await session.execute(query.limit(limit))
    reviews = result.scalars().all()

    for review in reviews:
        review_data = ReviewSchema.model_validate(review).model_dump_json()
        
        # Format as Server-Sent Event (SSE)
        yield f"event: review\ndata: {review_data}\n\n"
        
        # Minimized delay for high-volume streaming
        await asyncio.sleep(0.001)

    # Signal completion
    yield "event: done\ndata: completed\n\n"

# --------------------------- Fetch Reviews API ---------------------------
@router.get("", response_model=List[ReviewSchema])
async def get_reviews(
    company_id: int = Query(...),
    start: Optional[date] = Query(None),
    end: Optional[date] = Query(None),
    # Set to 50,000 to ensure 100% of data is fetched for full analysis
    limit: int = Query(50000), 
    session: AsyncSession = Depends(get_session),
):
    """
    Standard GET endpoint for static review loading.
    Fetches the entire company history for the dashboard's KPIs and charts.
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
    # Match the high limit to stream the entire company dataset
    limit: int = Query(50000), 
    session: AsyncSession = Depends(get_session),
):
    """
    SSE Endpoint for live streaming data to the dashboard.
    """
    return StreamingResponse(
        review_streamer(company_id, start, end, limit, session),
        media_type="text/event-stream"
    )

# --------------------------- Ingest Reviews API ---------------------------
@router.post("/ingest/{company_id}")
async def ingest_reviews(
    company_id: int,
    # Ceiling increased to 1000 for broader initial ingestion
    max_reviews: int = Query(1000), 
    session: AsyncSession = Depends(get_session),
):
    """
    Trigger the background ingestion service via Outscraper.
    """
    result = await session.execute(select(Company).where(Company.id == company_id))
    company = result.scalars().first()
    
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    try:
        # Calls the logic from app/services/review.py
        new_count = await ingest_outscraper_reviews(company, session, max_reviews=max_reviews)
        return {
            "status": "success",
            "message": f"✅ Stored {new_count} new reviews for {company.name}"
        }
    except Exception as e:
        logger.error(f"Ingestion Error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Ingestion service error: {str(e)}")
