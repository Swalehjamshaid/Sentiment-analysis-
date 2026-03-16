# filename: app/routes/reviews.py

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.models import Company
from app.core.db import get_session
from app.services.review import ingest_outscraper_reviews

logger = logging.getLogger("app.routes.reviews")
router = APIRouter(prefix="/api/reviews", tags=["reviews"])


@router.get("/")
async def fetch_reviews(
    company_id: int = Query(..., description="ID of the company"),
    start: Optional[str] = Query(None, description="Start date YYYY-MM-DD"),
    end: Optional[str] = Query(None, description="End date YYYY-MM-DD"),
    limit: int = Query(50, description="Maximum number of reviews to fetch"),
    session: AsyncSession = Depends(get_session),
):
    """
    Fetch Outscraper reviews for a given company and save them into Postgres.
    Returns number of new reviews inserted.
    """
    # 1️⃣ Fetch company
    result = await session.execute(select(Company).where(Company.id == company_id))
    company = result.scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    # 2️⃣ Ingest reviews
    try:
        new_count = await ingest_outscraper_reviews(company, session, max_reviews=limit)
    except Exception as e:
        logger.exception("Failed to fetch/save reviews for company %s: %s", company_id, e)
        raise HTTPException(status_code=500, detail="Failed to fetch reviews")

    # 3️⃣ Return response
    return {
        "company_id": company_id,
        "company_name": company.name,
        "new_reviews_saved": new_count,
    }
