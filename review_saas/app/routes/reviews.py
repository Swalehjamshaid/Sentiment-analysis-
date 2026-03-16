# filename: app/routes/reviews.py

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.db import get_session
from app.core.models import Company, Review
from app.services.review import ingest_outscraper_reviews

logger = logging.getLogger("app.routes.reviews")

router = APIRouter(prefix="/api/reviews", tags=["reviews"])

# ---------------------------
# GET reviews for a company
# ---------------------------
@router.get("/")
async def list_reviews(
    company_id: int = Query(..., description="Company ID to fetch reviews"),
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
):
    # Verify company exists
    result = await session.execute(select(Company).where(Company.id == company_id))
    company = result.scalars().first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    # Filter by dates if provided
    query = select(Review).where(Review.company_id == company_id)
    if start:
        query = query.where(Review.created_at >= start)
    if end:
        query = query.where(Review.created_at <= end)

    query = query.limit(limit)
    result = await session.execute(query)
    reviews = result.scalars().all()

    return [
        {
            "id": r.id,
            "author": r.author,
            "rating": r.rating,
            "text": r.text,
            "created_at": r.created_at,
        }
        for r in reviews
    ]


# ---------------------------
# POST fetch & save reviews from Outscraper
# ---------------------------
@router.post("/fetch")
async def fetch_and_save_reviews(
    company_id: int = Query(..., description="Company ID to fetch reviews"),
    background_tasks: BackgroundTasks = None,
):
    """
    Fetch reviews from Outscraper for a given company and save them into Postgres.
    Runs in background if background_tasks is provided.
    """

    async def _task(company_id: int):
        async with get_session() as session:
            result = await session.execute(select(Company).where(Company.id == company_id))
            company = result.scalars().first()
            if not company:
                logger.warning("Company %s not found for review fetch", company_id)
                return 0

            new_count = await ingest_outscraper_reviews(company, session)
            logger.info("Saved %s new reviews for company %s", new_count, company_id)
            return new_count

    if background_tasks:
        background_tasks.add_task(_task, company_id)
        return {"status": "background task started"}

    # synchronous call
    new_reviews = await _task(company_id)
    return {"status": "completed", "new_reviews": new_reviews}
