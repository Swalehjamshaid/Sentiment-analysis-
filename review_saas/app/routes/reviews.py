# filename: app/routes/reviews.py

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
import logging
import httpx
import os

from app.core.db import get_session
from app.core.models import Company, Review

router = APIRouter()
logger = logging.getLogger("reviews_routes")
logger.setLevel(logging.INFO)

# -------------------------
# Outscaper API Config
# -------------------------
OUTSCAPER_API_KEY = os.getenv("OUTSCAPER_API_KEY", "")
OUTSCAPER_REVIEWS_URL = "https://api.outscaper.com/v1/reviews"  # hypothetical endpoint

# -------------------------
# Helper Functions
# -------------------------
async def fetch_outscaper_reviews(place_id: str, limit: int = 50) -> List[dict]:
    """Fetch reviews from Outscaper API for a specific place_id."""
    headers = {"Authorization": f"Bearer {OUTSCAPER_API_KEY}"}
    params = {"place_id": place_id, "limit": limit}
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(OUTSCAPER_REVIEWS_URL, headers=headers, params=params)
            resp.raise_for_status()
            data = resp.json()
            return data.get("reviews", [])
    except httpx.HTTPError as e:
        logger.error(f"Outscaper API request failed: {e}")
        return []

async def add_review_to_db(review: dict, company_id: int, session: AsyncSession):
    """Insert a single review into PostgreSQL if not exists."""
    try:
        # check duplicate using author_name + review_time
        result = await session.execute(
            select(Review).where(
                Review.company_id == company_id,
                Review.author_name == review.get("author_name"),
                Review.review_time == review.get("review_time")
            )
        )
        exists = result.scalar_one_or_none()
        if exists:
            return

        new_review = Review(
            company_id=company_id,
            author_name=review.get("author_name"),
            text=review.get("text"),
            rating=review.get("rating"),
            sentiment_score=review.get("sentiment_score", 0),
            review_time=review.get("review_time")
        )
        session.add(new_review)
        await session.commit()
    except Exception as e:
        logger.error(f"Failed to insert review: {e}")

# -------------------------
# Routes
# -------------------------
@router.get("/reviews")
async def get_reviews(company_id: int, limit: int = 50, session: AsyncSession = Depends(get_session)):
    """Fetch reviews from DB for a given company."""
    try:
        result = await session.execute(select(Review).where(Review.company_id == company_id).limit(limit))
        reviews = result.scalars().all()
        return {"feed": [r.__dict__ for r in reviews]}
    except Exception as e:
        logger.error(f"Failed fetching reviews: {e}")
        raise HTTPException(status_code=500, detail="Failed fetching reviews")

@router.post("/reviews/sync")
async def sync_reviews(company_id: int, limit: int = 50, session: AsyncSession = Depends(get_session)):
    """Fetch reviews from Outscaper and store them in Postgres."""
    try:
        result = await session.execute(select(Company).where(Company.id == company_id))
        company = result.scalar_one_or_none()
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        reviews = await fetch_outscaper_reviews(company.place_id, limit)
        for review in reviews:
            await add_review_to_db(review, company_id, session)

        return {"status": "success", "fetched": len(reviews)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed syncing reviews: {e}")
        raise HTTPException(status_code=500, detail="Failed syncing reviews")
