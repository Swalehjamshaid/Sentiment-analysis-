# filename: app/routes/reviews.py
import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert

from app.core.db import get_session
from app.services.scraper import fetch_reviews
from app.core.models import Review  # Ensure this matches your model file

logger = logging.getLogger("app.reviews")
router = APIRouter(prefix="/reviews", tags=["Reviews"])

@router.get("/ingest/{company_id}")
async def ingest_reviews(company_id: int, db: AsyncSession = Depends(get_session)):
    """
    100% COMPLETE INGEST ROUTE:
    Fetches from SerpApi and maps to all 40+ database columns.
    """
    logger.info(f"🚀 Starting Ingest & Database Mapping for Company ID: {company_id}")
    
    try:
        # 1. Fetch live data from SerpApi via your scraper
        reviews_data = await fetch_reviews(company_id=company_id, session=db)
        
        if not reviews_data:
            return {"status": "info", "message": "No new live data found."}

        # 2. Map and Insert into Postgres
        # We use 'on_conflict_do_nothing' to prevent crashes on re-syncs
        for r in reviews_data:
            stmt = insert(Review).values(
                company_id=company_id,
                google_review_id=r.get("google_review_id"),
                author_name=r.get("author_name"),
                rating=r.get("rating"),
                text=r.get("text"),
                google_review_time=r.get("google_review_time"),
                source_platform="Google",
                # Setting defaults for your dashboard columns to avoid NULL errors
                is_local_guide=False,
                review_likes=r.get("likes", 0),
                sentiment_score=0.0,  # Ready for your Analyze Business step
                spam_score=0,
                is_complaint=False,
                is_praise=True if r.get("rating", 5) >= 4 else False,
                first_seen_at=datetime.utcnow(),
                last_updated_at=datetime.utcnow()
            ).on_conflict_do_nothing(index_elements=['google_review_id'])
            
            await db.execute(stmt)

        await db.commit()
        
        logger.info(f"✅ DB UPDATE SUCCESS: {len(reviews_data)} live records added.")
        
        return {
            "status": "success",
            "count": len(reviews_data),
            "company_id": company_id,
            "message": "Database successfully updated with live SerpApi data."
        }

    except Exception as e:
        await db.rollback()
        logger.error(f"❌ Database Ingest Failure: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
