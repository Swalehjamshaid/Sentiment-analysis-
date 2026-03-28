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
    DEEP INGEST: Fetches 100 reviews and FORCES a Postgres Commit.
    """
    logger.info(f"🚀 Database Sync Triggered for Company ID: {company_id}")
    
    try:
        # 1. Fetch data from SerpApi via Scraper
        # Note: target_limit=100 ensures we get the full batch
        data = await fetch_reviews(company_id=company_id, session=db, target_limit=100)
        
        if not data:
            logger.warning("⚠️ Scraper returned 0 results.")
            return {"status": "info", "message": "No reviews found."}

        # 2. THE FIX: USE AN ATOMIC TRANSACTION
        # async with db.begin() ensures that if the loop finishes, it COMMITS to disk.
        async with db.begin():
            new_saved_count = 0
            
            for r in data:
                # Prepare the PostgreSQL UPSERT (Insert or Update)
                # Matches your exact columns from the Railway screenshots
                stmt = insert(Review).values(
                    company_id=company_id,
                    google_review_id=r["google_review_id"],
                    author_name=r["author_name"],
                    rating=r["rating"],
                    text=r["text"],
                    google_review_time=r["google_review_time"],
                    review_likes=r.get("likes", 0),
                    source_platform="Google",
                    # Sentiment defaults for your dashboard
                    is_praise=True if r["rating"] >= 4 else False,
                    is_complaint=True if r["rating"] <= 2 else False,
                    first_seen_at=datetime.utcnow(),
                    last_updated_at=datetime.utcnow()
                ).on_conflict_do_nothing(index_elements=['google_review_id'])
                
                result = await db.execute(stmt)
                
                # Check if this was a new row or a duplicate
                if result.rowcount > 0:
                    new_saved_count += 1

            logger.info(f"✅ Transaction Finished: {new_saved_count} new reviews stored in Postgres.")

        return {
            "status": "success", 
            "total_fetched": len(data), 
            "newly_saved": new_saved_count,
            "message": "Data is now permanent in your Railway Postgres database."
        }

    except Exception as e:
        logger.error(f"❌ CRITICAL DATABASE ERROR: {str(e)}", exc_info=True)
        # We don't need to manually rollback because 'async with db.begin()' handles it
        raise HTTPException(status_code=500, detail=f"Postgres Write Failed: {str(e)}")
