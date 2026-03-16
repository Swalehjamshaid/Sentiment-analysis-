from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.db import get_session
from app.core.models import Review, Company  # make sure you have a Company model

router = APIRouter(prefix="/api/reviews")


async def save_reviews_to_db(session: AsyncSession, company_id: str, reviews: list[dict]):
    """Save reviews to PostgreSQL, avoid duplicates by review_id"""
    saved = []
    for r in reviews:
        # Avoid duplicate
        existing = await session.execute(
            select(Review).where(Review.review_id == r.get("review_id"))
        )
        if existing.scalars().first():
            continue

        review_date = r.get("review_time")
        if review_date:
            try:
                review_date = datetime.fromisoformat(review_date.split("T")[0])
            except Exception:
                review_date = datetime.utcnow()

        new_review = Review(
            company_id=company_id,
            review_id=r.get("review_id"),
            author_name=r.get("author_name"),
            rating=float(r.get("rating", 0)),
            text=r.get("text", ""),
            review_time=review_date,
            sentiment_score=float(r.get("sentiment_score", 0)),
        )
        session.add(new_review)
        saved.append(new_review)

    if saved:
        await session.commit()
    return saved


@router.get("/")
async def get_reviews(
    request: Request,
    company_id: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    limit: int = 50,
    session_db: AsyncSession = Depends(get_session),
):
    """Fetch reviews from Outscraper and save to DB"""
    # Get Outscraper client
    client = getattr(request.app.state, "reviews_client", None)
    if not client:
        raise HTTPException(status_code=500, detail="Reviews client not configured")

    # Optional: parse start/end dates
    start_date = datetime.fromisoformat(start) if start else None
    end_date = datetime.fromisoformat(end) if end else None

    # Fetch company
    async with session_db as session:
        result = await session.execute(select(Company).where(Company.id == company_id))
        company = result.scalars().first()
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

    # Fetch reviews from Outscraper
    reviews = await client.fetch_reviews(company.google_place_id, max_reviews=limit)

    # Filter by date if given
    if start_date or end_date:
        filtered = []
        for r in reviews:
            rt_str = r.get("review_time")
            if not rt_str:
                continue
            try:
                rt = datetime.fromisoformat(rt_str.split("T")[0])
            except Exception:
                rt = datetime.utcnow()
            if start_date and rt < start_date:
                continue
            if end_date and rt > end_date:
                continue
            filtered.append(r)
        reviews = filtered

    # Save to DB
    async with session_db as session:
        saved_reviews = await save_reviews_to_db(session, company_id, reviews)

    # Return reviews (most recent first)
    return {"feed": [dict(
        review_id=r.review_id,
        author_name=r.author_name,
        rating=r.rating,
        text=r.text,
        review_time=r.review_time.isoformat(),
        sentiment_score=r.sentiment_score
    ) for r in saved_reviews]}
