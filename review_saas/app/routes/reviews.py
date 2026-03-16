# filename: app/routes/reviews.py

from __future__ import annotations
import logging
from typing import Optional, List
from datetime import date

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.db import get_session
from app.core.models import Company, Review
from app.services.review import ingest_outscraper_reviews

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/reviews", tags=["reviews"])

# --------------------------- Fetch Reviews API ---------------------------
@router.get("/", response_model=List[Review])
async def get_reviews(
    company_id: int = Query(...),
    start: Optional[date] = Query(None),
    end: Optional[date] = Query(None),
    limit: int = Query(50),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(Review).where(Review.company_id == company_id))
    reviews = result.scalars().all()

    # Filter by date if requested
    if start:
        reviews = [r for r in reviews if r.date >= start]
    if end:
        reviews = [r for r in reviews if r.date <= end]

    return reviews[:limit]


# --------------------------- Ingest Reviews API ---------------------------
@router.post("/ingest/{company_id}")
async def ingest_reviews(
    company_id: int,
    max_reviews: int = Query(200, description="Maximum number of reviews to fetch"),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(Company).where(Company.id == company_id))
    company = result.scalars().first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    new_count = await ingest_outscraper_reviews(company, session, max_reviews=max_reviews)
    return {"message": f"✅ Stored {new_count} new reviews for company_id={company_id}"}


# --------------------------- Ingest All Companies ---------------------------
@router.post("/ingest_all")
async def ingest_all_reviews(
    max_reviews: int = Query(200, description="Maximum number of reviews per company"),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(Company))
    companies = result.scalars().all()
    total_new = 0

    for company in companies:
        new_count = await ingest_outscraper_reviews(company, session, max_reviews=max_reviews)
        total_new += new_count

    return {"message": f"✅ Stored {total_new} new reviews for all companies"}
