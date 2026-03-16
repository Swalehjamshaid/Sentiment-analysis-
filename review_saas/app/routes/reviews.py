from datetime import datetime
from typing import Optional
import logging
from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.db import get_session
from app.core.models import Review, Company

# Setup logging
logger = logging.getLogger("app.api.reviews")
router = APIRouter(prefix="/api/reviews")

async def save_reviews_to_db(session: AsyncSession, company_id: str, reviews: list[dict]):
    """
    Save reviews to PostgreSQL. 
    Synchronized with Review class in models.py
    """
    saved = []
    logger.info(f"📊 Processing {len(reviews)} reviews for company_id: {company_id}")

    for r in reviews:
        # 1. Get unique ID from Outscraper (usually 'review_id')
        ext_id = r.get("review_id")
        if not ext_id:
            logger.warning("⚠️ Review skipped: No review_id found in data")
            continue
            
        # 2. Check for duplicates using google_review_id
        existing = await session.execute(
            select(Review).where(Review.google_review_id == ext_id)
        )
        if existing.scalars().first():
            continue

        # 3. Handle the date for google_review_time
        review_date_str = r.get("review_time")
        if review_date_str:
            try:
                # Standardizing ISO format
                review_date = datetime.fromisoformat(review_date_str.replace("Z", "+00:00"))
            except Exception:
                review_date = datetime.utcnow()
        else:
            review_date = datetime.utcnow()

        # 4. Map Outscraper data to models.py fields
        new_review = Review(
            company_id=int(company_id),
            google_review_id=ext_id,
            review_url=r.get("review_link"),
            author_name=r.get("author_title") or r.get("author_name", "Anonymous"),
            author_id=r.get("author_id"),
            author_url=r.get("author_link"),
            rating=int(r.get("review_rating") or r.get("rating") or 0),
            text=r.get("review_text") or r.get("text", ""),
            google_review_time=review_date,
            sentiment_score=float(r.get("sentiment_score", 0)),
            source_platform="Google",
            review_likes=int(r.get("review_likes", 0)),
            owner_answer=r.get("owner_answer")
        )
        session.add(new_review)
        saved.append(new_review)

    if saved:
        try:
            await session.commit()
            logger.info(f"✅ Successfully saved {len(saved)} reviews to database")
            for r in saved:
                await session.refresh(r)
        except Exception as e:
            await session.rollback()
            logger.error(f"❌ Database commit failed: {e}")
            raise HTTPException(status_code=500, detail="Database error occurred")
    else:
        logger.info("ℹ️ No new reviews were added (all exist or no data found)")
            
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
    
    # 1. Check client
    client = getattr(request.app.state, "reviews_client", None)
    if not client:
        raise HTTPException(status_code=500, detail="Reviews client not configured")

    # 2. Find company to get Google Place ID
    result = await session.execute(select(Company).where(Company.id == int(company_id)))
    company = result.scalars().first()
    if not company:
        raise HTTPException(status_code=404, detail=f"Company {company_id} not found")

    # 3. Call Outscraper
    try:
        logger.info(f"🔎 Fetching reviews for Place ID: {company.google_place_id}")
        raw_reviews = await client.fetch_reviews(company.google_place_id, max_reviews=limit)
    except Exception as e:
        logger.error(f"❌ Outscraper error: {e}")
        raise HTTPException(status_code=502, detail="External API error")

    # 4. Filtering logic
    start_date = datetime.fromisoformat(start) if start else None
    end_date = datetime.fromisoformat(end) if end else None

    if start_date or end_date:
        filtered = []
        for r in raw_reviews:
            rt_str = r.get("review_time")
            if not rt_str: continue
            try:
                rt = datetime.fromisoformat(rt_str.split("T")[0])
                if start_date and rt < start_date: continue
                if end_date and rt > end_date: continue
                filtered.append(r)
            except:
                continue
        raw_reviews = filtered

    # 5. Save and Return
    saved_reviews = await save_reviews_to_db(session, company_id, raw_reviews)

    return {
        "status": "success",
        "count": len(saved_reviews),
        "feed": [
            {
                "id": r.id,
                "google_review_id": r.google_review_id,
                "author_name": r.author_name,
                "rating": r.rating,
                "text": r.text,
                "review_time": r.google_review_time.isoformat() if r.google_review_time else None,
                "sentiment_score": r.sentiment_score
            } for r in saved_reviews
        ]
    }
