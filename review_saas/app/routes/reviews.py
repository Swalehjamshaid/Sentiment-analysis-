# filename: app/routes/reviews.py

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Dict, Any

from app.core.db import get_session
from app.core.models import Company, Review
from app.services.review import ingest_outscraper_reviews

router = APIRouter(prefix="/api/reviews", tags=["reviews"])

@router.get("/")
async def get_reviews(
    company_id: int,
    start: str = "",
    end: str = "",
    limit: int = 50,
    session: AsyncSession = Depends(get_session),
):
    """
    Fetch stored reviews for a company from the database.
    Supports optional start/end dates and limit.
    """
    query = select(Review).where(Review.company_id == company_id).limit(limit)
    result = await session.execute(query)
    reviews = result.scalars().all()
    return {"company_id": company_id, "reviews": [r.to_dict() for r in reviews]}

@router.post("/ingest/{company_id}")
async def ingest_reviews_for_company(
    company_id: int,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
):
    """
    Trigger Outscraper ingestion for a specific company.
    Runs ingestion in the background.
    """
    result = await session.execute(select(Company).where(Company.id == company_id))
    company = result.scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    # Add ingestion to background tasks
    background_tasks.add_task(ingest_outscraper_reviews, company, session)
    return {"status": "ingestion started", "company_id": company_id}

@router.post("/ingest_all")
async def ingest_reviews_for_all(
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
):
    """
    Trigger Outscraper ingestion for all companies.
    Each company is ingested in a background task.
    """
    result = await session.execute(select(Company))
    companies: List[Company] = result.scalars().all()
    if not companies:
        raise HTTPException(status_code=404, detail="No companies found")

    for company in companies:
        background_tasks.add_task(ingest_outscraper_reviews, company, session)

    return {"status": "ingestion started for all companies", "count": len(companies)}
