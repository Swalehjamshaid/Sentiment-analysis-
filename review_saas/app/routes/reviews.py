# filename: app/routes/reviews.py
import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import select, func

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
    logger.info(f"🚀 DATABASE SYNC START: Company ID {company_id}")
    
    try:
        # 1. Fetch 100 reviews from scraper
        data = await fetch_reviews(company_id=company_id, session=db, target_limit=100)
        
        if not data:
            return {"status": "info", "message": "No data found to save."}

        # 2. ATOMIC TRANSACTION: This forces the save to Railway
        async with db.begin():
            new_saved = 0
            for r in data:
                stmt = insert(Review).values(
                    company_id=company_id,
                    google_review_id=r["google_review_id"],
                    author_name=r["author_name"],
                    rating=r["rating"],
                    text=r["text"],
                    google_review_time=r["google_review_time"],
                    review_likes=r["likes"],
                    source_platform="Google",
                    # Metrics for Dashboard
                    is_praise=True if r["rating"] >= 4 else False,
                    is_complaint=True if r["rating"] <= 2 else False,
                    first_seen_at=datetime.utcnow(),
                    last_updated_at=datetime.utcnow()
                ).on_conflict_do_nothing(index_elements=['google_review_id'])
                
                result = await db.execute(stmt)
                if result.rowcount > 0:
                    new_saved += 1

        logger.info(f"✅ DATABASE SYNC COMPLETE: {new_saved} new records stored.")
        return {
            "status": "success", 
            "total_fetched": len(data), 
            "newly_saved": new_saved,
            "message": "100 reviews are now permanent in Postgres."
        }

    except Exception as e:
        logger.error(f"❌ DB Sync Failed: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/status/{company_id}")
async def get_db_count(company_id: int, db: AsyncSession = Depends(get_session)):
    """Verify how many reviews are actually in the DB."""
    res = await db.execute(select(func.count(Review.id)).where(Review.company_id == company_id))
    return {"total_in_db": res.scalar()}
