# filename: app/routes/reviews.py

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import Optional
from app.core.db import get_session
from app.core.models import Review, Company
from app.main import app  # to access app.state.reviews_client

router = APIRouter()


@router.get("/api/reviews")
async def get_reviews(
    company_id: str = Query(...),
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    limit: int = Query(50),
    session: AsyncSession = Depends(get_session),
):
    """Fetch reviews from Outscraper and save them to the database."""
    # 1️⃣ Fetch the company
    result = await session.execute(select(Company).where(Company.id == company_id))
    company = result.scalars().first()
    if not company:
        return {"feed": [], "saved_count": 0}

    # 2️⃣ Fetch reviews from Outscraper
    reviews_client = getattr(app.state, "reviews_client", None)
    if not reviews_client:
        return {"feed": [], "saved_count": 0}

    reviews_data = await reviews_client.fetch_reviews(company, max_reviews=limit)

    # 3️⃣ Filter by start/end date if provided
    if start or end:
        def in_range(r):
            date = r.get("review_time")
            if not date:
                return False
            if start and date < start:
                return False
            if end and date > end:
                return False
            return True
        reviews_data = [r for r in reviews_data if in_range(r)]

    # 4️⃣ Save new reviews to database
    saved_count = 0
    for r in reviews_data:
        # Avoid duplicates
        existing = await session.execute(
            select(Review).where(
                Review.company_id == company.id,
                Review.review_time == r.get("review_time"),
                Review.author_name == r.get("author_name"),
            )
        )
        if existing.scalars().first():
            continue

        review = Review(
            company_id=company.id,
            author_name=r.get("author_name"),
            rating=r.get("rating"),
            text=r.get("text"),
            review_time=r.get("review_time"),
            sentiment_score=r.get("sentiment_score", 0),
        )
        session.add(review)
        saved_count += 1

    if saved_count > 0:
        await session.commit()

    return {"feed": reviews_data, "saved_count": saved_count}
