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

# CRITICAL: redirect_slashes=False ensures Railway deployments don't loop on 307 redirects
router = APIRouter(prefix="/api/reviews", tags=["reviews"], redirect_slashes=False)

# --------------------------- Pydantic Schema ---------------------------
class ReviewSchema(BaseModel):
    """Matches the SQLAlchemy Review model for JSON response serialization"""
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
    Worker for the /stream endpoint.
    Fetches ALL existing data for the company and yields it to the dashboard.
    """
    # Query all stored reviews for this company ordered by newest first
    query = select(Review).where(Review.company_id == company_id).order_by(desc(Review.google_review_time))
    
    if start:
        query = query.where(Review.google_review_time >= start)
    if end:
        query = query.where(Review.google_review_time <= end)
    
    # We execute with the provided limit (default 50,000) to capture the full history
    result = await session.execute(query.limit(limit))
    reviews = result.scalars().all()

    for review in reviews:
        review_data = ReviewSchema.model_validate(review).model_dump_json()
        
        # Stream each review as a Server-Sent Event (SSE)
        yield f"event: review\ndata: {review_data}\n\n"
        
        # High speed streaming for large datasets
        await asyncio.sleep(0.001)

    # Signal completion to the frontend to finalize charts/analysis
    yield "event: done\ndata: completed\n\n"

# --------------------------- Fetch Reviews API ---------------------------
@router.get("", response_model=List[ReviewSchema])
async def get_reviews(
    company_id: int = Query(...),
    start: Optional[date] = Query(None),
    end: Optional[date] = Query(None),
    # INCREASED LIMIT: Default set to 50,000 to ensure full database is fetched for analysis
    limit: int = Query(50000), 
    session: AsyncSession = Depends(get_session),
):
    """
    Standard GET endpoint for the Analysis button. 
    Retrieves all reviews from Postgres for the specified company.
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
    # High limit to match the GET endpoint
    limit: int = Query(50000), 
    session: AsyncSession = Depends(get_session),
):
    """
    Real-time endpoint that streams all database reviews to the UI.
    """
    return StreamingResponse(
        review_streamer(company_id, start, end, limit, session),
        media_type="text/event-stream"
    )

# --------------------------- Ingest Reviews API ---------------------------
@router.post("/ingest/{company_id}")
async def ingest_reviews(
    company_id: int,
    # How many NEW reviews to fetch from Google Maps via Outscraper
    max_reviews: int = Query(1000), 
    session: AsyncSession = Depends(get_session),
):
    """
    Trigger ingestion of new reviews. 
    Duplicates are filtered in the service layer using existing DB records.
    """
    result = await session.execute(select(Company).where(Company.id == company_id))
    company = result.scalars().first()
    
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    try:
        # Calls the Producer-Consumer logic in app/services/review.py
        # Starting skip is calculated based on current DB count in the service
        new_count = await ingest_outscraper_reviews(company, session, max_reviews=max_reviews)
        return {
            "status": "success",
            "message": f"✅ Processed {new_count} new reviews for {company.name}"
        }
    except Exception as e:
        logger.error(f"Ingestion Error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Scraper error: {str(e)}")
