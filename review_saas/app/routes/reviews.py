from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.db import get_session
from app.core.models import Review, Company

router = APIRouter(prefix="/api/reviews")

async def save_reviews_to_db(session: AsyncSession, company_id: str, reviews: list[dict]):
    """Save reviews to PostgreSQL, avoid duplicates by review_id"""
    saved = []
    for r in reviews:
        # Check if review already exists to avoid Unique Constraint errors
        review_id = r.get("review_id")
        if not review_id:
            continue
            
        existing = await session.execute(
            select(Review).where(Review.review_id == review_id)
        )
        if existing.scalars().first():
            continue

        # Parse date
        review_date_str = r.get("review_time")
        if review_date_str:
            try:
                # Robust parsing for ISO strings
                review_date = datetime.fromisoformat(review_date_str.replace("Z", "+00:00").split("T")[0])
            except Exception:
                review_date = datetime.utcnow()
        else:
            review_date = datetime.utcnow()

        new_review = Review(
            company_id=company_id,
            review_id=review_id,
            author_name=r.get("author_name", "Anonymous"),
            rating=float(r.get("rating", 0)),
            text=r.get("text", ""),
            review_time=review_date,
            sentiment_score=float(r.get("sentiment_score", 0)),
        )
        session.add(new_review)
        saved.append(new_review)

    if saved:
        try:
            await session.commit()
            # Refresh to ensure objects are loaded with DB state for the return statement
            for r in saved:
                await session.refresh(r)
        except Exception as e:
            await session.rollback()
            print(f"Database Error: {e}")
            raise HTTPException(status_code=500, detail="Failed to save reviews to database")
            
    return saved

@router.get("/")
async def get_reviews(
    request: Request,
    company_id: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    limit: int = 50,
    session: AsyncSession = Depends(get_session),
):
    """Fetch reviews from Outscraper, save to DB, and return them"""
    
    # 1. Get Outscraper client from app state
    client = getattr(request.app.state, "reviews_client", None)
    if not client:
        raise HTTPException(status_code=500, detail="Reviews client not configured")

    # 2. Fetch company to get the Google Place ID
    result = await session.execute(select(Company).where(Company.id == company_id))
    company = result.scalars().first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    # 3. Fetch reviews from Outscraper API
    try:
        raw_reviews = await client.fetch_reviews(company.google_place_id, max_reviews=limit)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Outscraper error: {str(e)}")

    # 4. Optional: parse start/end dates for filtering
    start_date = datetime.fromisoformat(start) if start else None
    end_date = datetime.fromisoformat(end) if end else None

    # 5. Filter reviews if dates are provided
    if start_date or end_date:
        filtered = []
        for r in raw_reviews:
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
        raw_reviews = filtered

    # 6. Save to DB and get the instances back
    saved_reviews = await save_reviews_to_db(session, company_id, raw_reviews)

    # 7. Return the feed
    return {
        "status": "success",
        "count": len(saved_reviews),
        "feed": [
            {
                "review_id": r.review_id,
                "author_name": r.author_name,
                "rating": r.rating,
                "text": r.text,
                "review_time": r.review_time.isoformat() if r.review_time else None,
                "sentiment_score": r.sentiment_score
            } for r in saved_reviews
        ]
    }
