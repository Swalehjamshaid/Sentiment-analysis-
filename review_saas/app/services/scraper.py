# filename: app/routes/reviews.py
import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import text

from app.core.db import get_session
from app.services.scraper import fetch_reviews
from app.core.models import Review

logger = logging.getLogger("app.reviews")
router = APIRouter(prefix="/reviews", tags=["Reviews"])

@router.get("/ingest_100/{company_id}")
async def ingest_100_reviews(company_id: int, db: AsyncSession = Depends(get_session)):
    """
    DEEP INGEST: Fetches 100 reviews and forces a Postgres Commit.
    """
    logger.info(f"🚀 Database Sync Started for Company: {company_id}")
    
    try:
        # 1. Fetch data from Scraper
        data = await fetch_reviews(company_id=company_id, session=db, target_limit=100)
        
        if not data:
            logger.warning("⚠️ Scraper returned 0 results. Nothing to save.")
            return {"status": "info", "message": "No reviews found."}

        # 2. Use db.begin() to ensure an ATOMIC TRANSACTION
        # This is the most reliable way to save to Railway Postgres
        async with db.begin():
            saved_count = 0
            for r in data:
                # Prepare the insert statement with ON CONFLICT DO NOTHING
                # This prevents crashes if the review already exists
                stmt = insert(Review).values(
                    company_id=company_id,
                    google_review_id=r["google_review_id"],
                    author_name=r["author_name"],
                    rating=r["rating"],
                    text=r["text"],
                    google_review_time=r["google_review_time"],
                    review_likes=r.get("likes", 0),
                    source_platform="Google",
                    is_praise=True if r["rating"] >= 4 else False,
                    is_complaint=True if r["rating"] <= 2 else False,
                    first_seen_at=datetime.utcnow(),
                    last_updated_at=datetime.utcnow()
                ).on_conflict_do_nothing(index_elements=['google_review_id'])
                
                result = await db.execute(stmt)
                if result.rowcount > 0:
                    saved_count += 1

            logger.info(f"✅ Transaction Complete: {saved_count} new reviews written to disk.")

        return {
            "status": "success", 
            "fetched": len(data), 
            "new_saved": saved_count,
            "message": "Data is now permanent in Postgres."
        }

    except Exception as e:
        logger.error(f"❌ Critical Database Error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Database Sync Failed: {str(e)}")
