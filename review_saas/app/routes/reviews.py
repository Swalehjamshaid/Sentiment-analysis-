# filename: app/routes/reviews.py

from __future__ import annotations
import logging
from typing import Optional, List
from datetime import date

from fastapi import APIRouter, Depends, Query, HTTPException
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
    """Schema to safely serialize SQLAlchemy models to JSON"""
    id: int
    company_id: int
    content: Optional[str] = None
    rating: Optional[int] = None
    author_name: Optional[str] = None
    date: Optional[date] = None
    
    model_config = ConfigDict(from_attributes=True)

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
        query = query.where(Review.date >= start)
    if end:
        query = query.where(Review.date <= end)
    
    result = await session.execute(query.limit(limit))
    return result.scalars().all()

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

    # The service function now handles the database commit
    new_count = await ingest_outscraper_reviews(company, session, max_reviews=max_reviews)
    return {"message": f"✅ Stored {new_count} new reviews for {company.name}"}
