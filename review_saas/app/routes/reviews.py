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
    This helper is used by the /stream endpoint to push all data to the UI.
    """
    # Build the query to fetch all reviews for the specific company
    query = select(Review).where(Review.company_id == company_id).order_by(desc(Review.google_review_time))
    
    if start:
        query = query.where(Review.google_review_time >= start)
    if end:
        query = query.where(Review.google_review_time <= end)
    
    # Executing with a high limit to ensure the entire database history is captured
    result = await session.execute(query.limit(limit))
    reviews = result.scalars().all()

    for review in reviews:
        # Convert SQLAlchemy object to Pydantic and then to JSON string
        review_data = ReviewSchema.model_validate(review).model_dump_json()
        
        # Format as Server-Sent Event (SSE) for real-time frontend consumption
        yield f"event: review\ndata: {review_data}\n\n"
        
        # Minimized delay for high-volume streaming to prevent UI lag
        await asyncio.sleep(0.001)

    # Signal completion so the frontend knows the "Load" process is finished
    yield "event: done\ndata: completed\n\n"

# --------------------------- Fetch Reviews API ---------------------------
@router.get("", response_model=List[ReviewSchema])
async def get_reviews(
    company_id: int = Query(...),
    start: Optional[date] = Query(None),
    end: Optional[date] = Query(None),
    # INCREASED DEFAULT: Set to 50,000 to ensure 100% of data is fetched for the dashboard
    limit: int = Query(50000), 
    session: AsyncSession = Depends(get_session),
):
    """
    Standard GET endpoint for static review loading.
    Used for calculating KPIs, charts, and initial data tables.
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
    # MATCHING LIMIT: Ensures the stream doesn't cut off earlier than the static API
    limit: int = Query(50000), 
    session: AsyncSession = Depends(get_session),
):
    """
    SSE Endpoint for live streaming data. 
    When you press "Load" on the dashboard, this handles the sequential display of all reviews.
    """
    return StreamingResponse(
        review_streamer(company_id, start, end, limit, session),
        media_type="text/event-stream"
    )

# --------------------------- Ingest Reviews API ---------------------------
@router.post("/ingest/{company_id}")
async def ingest_reviews(
    company_id: int,
    # Ceiling for how many NEW reviews to pull from Google Maps via Outscraper
    max_reviews: int = Query(1000), 
    session: AsyncSession = Depends(get_session),
):
    """
    Trigger the background ingestion service. 
    This adds new reviews to the database without deleting existing ones.
    """
    result = await session.execute(select(Company).where(Company.id == company_id))
    company = result.scalars().first()
    
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    try:
        # Calls the Producer-Consumer logic in app/services/review.py
        new_count = await ingest_outscraper_reviews(company, session, max_reviews=max_reviews)
        return {
            "status": "success",
            "message": f"✅ Stored {new_count} new reviews for {company.name}"
        }
    except Exception as e:
        logger.error(f"Ingestion Error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Ingestion service failure: {str(e)}")
