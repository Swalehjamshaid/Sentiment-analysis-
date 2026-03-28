# filename: app/routes/reviews.py
import logging
from datetime import datetime
from typing import List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import select

# Internal imports - Ensure these match your project structure
from app.core.db import get_session
from app.services.scraper import fetch_reviews
from app.core.models import Review, Company

logger = logging.getLogger("app.reviews")

# Router definition - internal prefix set to /reviews
router = APIRouter(prefix="/reviews", tags=["Reviews"])

@router.get("/ingest_100/{company_id}")
async def ingest_100_reviews(company_id: int, db: AsyncSession = Depends(get_session)):
    """
    DEEP INGEST & PERMANENT STORAGE:
    1. Fetches 100 reviews via SerpApi scraper.
    2. Opens an Atomic Transaction (db.begin) to force a save to Postgres.
    3. Maps columns to ensure the Dashboard displays real data.
    """
    logger.info(f"🚀 DATABASE SYNC INITIATED: Company ID {company_id}")
    
    try:
        # 1. Fetch the data from your Scraper
        # This calls the paginated loop we built in scraper.py
        data = await fetch_reviews(company_id=company_id, session=db, target_limit=100)
        
        if not data:
            logger.warning("⚠️ Scraper returned 0 results. Check SerpApi credits or query.")
            return {"status": "info", "message": "No reviews found."}

        logger.info(f"🛰️ Scraper success: Found {len(data)} reviews. Committing to Postgres...")

        # 2. THE ATOMIC COMMIT: Use db.begin() to ensure data is permanently written
        # This is the fix for "results fetched but not saved"
        async with db.begin():
            new_saved_count = 0
            
            for r in data:
                # Prepare the PostgreSQL UPSERT (Insert or Update)
                stmt = insert(Review).values(
                    company_id=company_id,
                    google_review_id=r.get("google_review_id"),
                    author_name=r.get("author_name"),
                    rating=r.get("rating"),
                    text=r.get("text"),
                    google_review_time=r.get("google_review_time"),
                    review_likes=r.get("likes", 0),
                    source_platform="Google",
                    # UI Logic: Populates the 'Emotion Radar' on your dashboard
                    is_praise=True if r.get("rating", 5) >= 4 else False,
                    is_complaint=True if r.get("rating", 5) <= 2 else False,
                    # Timestamps for the 'Sentiment Trend' graphs
                    first_seen_at=datetime.utcnow(),
                    last_updated_at=datetime.utcnow(),
                    sentiment_score=0.0,
                    spam_score=0,
                    is_local_guide=False
                ).on_conflict_do_nothing(index_elements=['google_review_id'])
                
                # Execute the specific insert
                result = await db.execute(stmt)
                
                # Only increment if a new row was actually added to the disk
                if result.rowcount > 0:
                    new_saved_count += 1

            logger.info(f"✅ TRANSACTION COMPLETE: {new_saved_count} new records stored.")

        # 3. Final JSON Response
        return {
            "status": "success", 
            "total_fetched": len(data), 
            "newly_saved": new_saved_count,
            "message": f"Successfully pushed {new_saved_count} new reviews to the dashboard."
        }

    except Exception as e:
        logger.error(f"❌ CRITICAL DATABASE ERROR: {str(e)}", exc_info=True)
        # SQLAlchemy handles rollback automatically inside 'async with db.begin()'
        raise HTTPException(status_code=500, detail=f"Postgres Write Failed: {str(e)}")

@router.get("/status/{company_id}")
async def get_sync_status(company_id: int, db: AsyncSession = Depends(get_session)):
    """Check how many reviews are currently in the DB for this company."""
    from sqlalchemy import func
    result = await db.execute(select(func.count(Review.id)).where(Review.company_id == company_id))
    count = result.scalar()
    return {"company_id": company_id, "total_records_in_db": count}
