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
from sqlalchemy import select
from pydantic import BaseModel, ConfigDict

from app.core.db import get_session
from app.core.models import Company, Review
from app.services.review import ingest_outscraper_reviews

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/reviews", tags=["reviews"])

# --------------------------- Pydantic Schema ---------------------------
class ReviewSchema(BaseModel):
    """Matches your SQLAlchemy Review model exactly"""
    id: int
    company_id: int
    google_review_id: str
    author_name: Optional[str] = None
    rating: Optional[int] = None
    text: Optional[str] = None
    google_review_time: Optional[datetime] = None
    sentiment_score: Optional[float] = 0.0  # Added for analysis
    
    model_config = ConfigDict(from_attributes=True)

# --------------------------- Streaming Helper ---------------------------
async def review_streamer(company_id: int, start: date, end: date, limit: int, session: AsyncSession):
    """
    Query the database and yield reviews one-by-one as SSE events.
    """
    query = select(Review).where(Review.company_id == company_id)
    
    if start:
        query = query.where(Review.google_review_time >= start)
    if end:
        query = query.where(Review.google_review_time <= end)
    
    result = await session.execute(query.limit(limit))
    reviews = result.scalars().all()

    for i, review in enumerate(reviews):
        # Convert Pydantic model to dict, then to JSON
        review_data = ReviewSchema.model_validate(review).model_dump_json()
        
        # Format as Server-Sent Event
        yield f"event: review\ndata: {review_data}\n\n"
        
        # Artificial delay to simulate processing and let the UI animate
        await asyncio.sleep(0.05)

    yield "event: done\ndata: completed\n\n"

# --------------------------- Fetch Reviews API ---------------------------
@router.get("/", response_model=List[ReviewSchema])
async def get_reviews(
    company_id: int = Query(...),
    start: Optional[date] = Query(None),
    end: Optional[date] = Query(None),
    limit: int = Query(50),
    session: AsyncSession = Depends(get_session),
):
    query = select(Review).where(Review.company_id == company_id)
    
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
    result = await session.execute(select(Company).where(Company.id == company_id))
    company = result.scalars().first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    new_count = await ingest_outscraper_reviews(company, session, max_reviews=max_reviews)
    return {"message": f"✅ Stored {new_count} new reviews for {company.name}"}
