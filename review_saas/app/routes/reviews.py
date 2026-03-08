# File: app/routes/reviews.py

from fastapi import APIRouter, HTTPException, Query, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from typing import List, Optional, Dict, Any
from collections import Counter
from datetime import datetime

from app.core.db import get_session
from app.core.models import Review, Company
from app.services.google_reviews import OutscraperReviewsService, ReviewData


# ---------------------------------------------------------
# Mock API client (Replace with real Outscraper client)
# ---------------------------------------------------------
class MockClient:

    def get_reviews(self, place_id, limit, offset):
        return {
            "reviews": [
                {
                    "review_id": f"rev_{offset+i}",
                    "author_name": f"Author {i}",
                    "rating": 3 + (i % 3),
                    "text": f"Sample review {i}",
                    "time": 1700000000 + (i * 2000),
                    "title": f"Title {i}",
                    "helpful_votes": i % 3,
                    "platform": "Google",
                    "competitor_name": f"Competitor {i%2}" if i % 2 == 0 else None
                } for i in range(limit)
            ]
        }


# ---------------------------------------------------------
# Initialize services
# ---------------------------------------------------------
api_client = MockClient()
outscraper_service = OutscraperReviewsService(api_client)

router = APIRouter(prefix="/api/reviews", tags=["reviews"])


# ---------------------------------------------------------
# Ingest Reviews Based on Date Range
# ---------------------------------------------------------
@router.post("/ingest")
async def ingest_reviews(
        place_id: str,
        company_id: int,
        competitor_place_ids: Optional[List[str]] = Query(None),
        start_date: Optional[str] = Query(None),
        end_date: Optional[str] = Query(None),
        limit: int = Query(500),
        db: AsyncSession = Depends(get_session)
):
    """
    Fetch reviews from Outscraper and store them in DB
    based on the date range provided by frontend.
    """

    try:

        # Validate company
        result = await db.execute(select(Company).filter(Company.id == company_id))
        company = result.scalars().first()

        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        start_dt = datetime.fromisoformat(start_date) if start_date else None
        end_dt = datetime.fromisoformat(end_date) if end_date else None

        places = [place_id]

        if competitor_place_ids:
            places.extend(competitor_place_ids)

        total_saved = 0
        total_fetched = 0

        for place in places:

            reviews_data: List[ReviewData] = await outscraper_service.fetch_reviews(
                place,
                max_reviews=limit
            )

            total_fetched += len(reviews_data)

            for r in reviews_data:

                review_date = r.time_created

                # Filter based on date range
                if start_dt and review_date < start_dt:
                    continue

                if end_dt and review_date > end_dt:
                    continue

                review_id = r.review_id

                exist = await db.execute(
                    select(Review).filter(
                        Review.external_review_id == review_id
                    )
                )

                if exist.scalars().first():
                    continue

                review = Review(
                    company_id=company_id,
                    external_review_id=review_id,
                    author=r.author_name,
                    rating=r.rating,
                    review_text=r.text,
                    review_date=review_date,
                    sentiment=None,
                    competitor_name=r.competitor_name
                )

                db.add(review)
                total_saved += 1

        await db.commit()

        return {
            "status": "success",
            "reviews_fetched": total_fetched,
            "reviews_saved": total_saved,
            "date_range": {
                "start_date": start_date,
                "end_date": end_date
            }
        }

    except Exception as e:

        await db.rollback()

        raise HTTPException(
            status_code=500,
            detail=f"Failed to ingest reviews: {str(e)}"
        )


# ---------------------------------------------------------
# Review Feed for Dashboard
# ---------------------------------------------------------
@router.get("/feed/{company_id}")
async def get_reviews_feed(
        company_id: int,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 20,
        db: AsyncSession = Depends(get_session)
):
    """
    Returns filtered reviews for the dashboard.
    """

    query = select(Review).filter(Review.company_id == company_id)

    if start_date:
        query = query.filter(
            Review.review_date >= datetime.fromisoformat(start_date)
        )

    if end_date:
        query = query.filter(
            Review.review_date <= datetime.fromisoformat(end_date)
        )

    query = query.order_by(
        Review.review_date.desc()
    ).limit(limit)

    result = await db.execute(query)

    reviews = result.scalars().all()

    return {
        "status": "success",
        "reviews": [
            {
                "id": r.id,
                "author": r.author,
                "rating": r.rating,
                "text": r.review_text,
                "date": r.review_date,
                "sentiment": r.sentiment,
                "competitor": r.competitor_name
            }
            for r in reviews
        ]
    }


# ---------------------------------------------------------
# Competitor Analytics API
# ---------------------------------------------------------
@router.get("/competitors/{company_id}")
async def competitor_stats(
        company_id: int,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        db: AsyncSession = Depends(get_session)
):
    """
    Returns competitor review counts and ratings.
    """

    query = select(Review).filter(
        Review.company_id == company_id,
        Review.competitor_name != None
    )

    if start_date:
        query = query.filter(
            Review.review_date >= datetime.fromisoformat(start_date)
        )

    if end_date:
        query = query.filter(
            Review.review_date <= datetime.fromisoformat(end_date)
        )

    result = await db.execute(query)

    reviews = result.scalars().all()

    competitor_counts = Counter(
        r.competitor_name for r in reviews if r.competitor_name
    )

    competitor_ratings: Dict[str, List[int]] = {}

    for r in reviews:

        if r.competitor_name:

            competitor_ratings.setdefault(
                r.competitor_name,
                []
            ).append(r.rating)

    competitor_avg = {
        name: round(sum(vals) / len(vals), 2)
        for name, vals in competitor_ratings.items()
    }

    return {
        "competitor_review_count": competitor_counts,
        "competitor_avg_rating": competitor_avg
    }
