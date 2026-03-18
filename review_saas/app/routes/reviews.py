# filename: app/routes/reviews.py
from fastapi import APIRouter, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_session
from app.core.models import Company
from app.services import scraper  # make sure scraper.py exists

router = APIRouter(prefix="/reviews", tags=["Reviews"])

@router.post("/ingest/{company_id}")
async def ingest_reviews(company_id: int, limit: int = 300, skip: int = 0, session: AsyncSession = get_session()):
    # Fetch company from DB
    company = await session.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    # Determine which ID to use
    place_id = company.google_id or getattr(company, "place_id", None) or getattr(company, "place_url", None)
    if not place_id:
        raise HTTPException(
            status_code=400,
            detail="Company does not have google_id, place_id, or place_url. Please update the database."
        )

    try:
        # Fetch reviews from scraper
        reviews = await scraper.fetch_reviews(place_id=place_id, limit=limit, skip=skip)

        if not reviews:
            return {"message": "No reviews found for this company", "count": 0}

        # Here you can insert reviews into DB
        # Example:
        # for r in reviews:
        #     review_obj = Review(**r, company_id=company.id)
        #     session.add(review_obj)
        # await session.commit()

        return {"message": f"{len(reviews)} reviews fetched successfully", "count": len(reviews)}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching reviews: {e}")
