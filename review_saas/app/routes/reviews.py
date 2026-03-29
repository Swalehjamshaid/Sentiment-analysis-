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

# Router definition
router = APIRouter(prefix="/reviews", tags=["Reviews"])

@router.get("/ingest_100/{company_id}")
async def ingest_100_reviews(company_id: int, db: AsyncSession = Depends(get_session)):
    """
    100% COMPLETE INGEST:
    Triggers the SerpApi scraper and FORCES the Postgres save.
    """
    logger.info(f"🚀 MANUAL TRIGGER: Ingesting 100 reviews for Company {company_id}")
    
    try:
        # 1. Fetch 100 reviews from your scraper
        # This will now appear in your logs as soon as you hit the URL
        data = await fetch_reviews(company_id=company_id, session=db, target_limit=100)
        
        if not data:
            logger.warning("⚠️ Scraper returned 0 reviews. Check SerpApi API Key/Credits.")
            return {"status": "info", "message": "No reviews found to fetch."}

        # 2. FORCE THE SAVE (The Atomic Transaction)
        # This is the fix for "fetched but not saved"
        async with db.begin():
            new_count = 0
            for r in data:
                stmt = insert(Review).values(
                    company_id=company_id,
                    google_review_id=r["google_review_id"],
                    author_name=r["author_name"],
                    rating=r["rating"],
                    text=r["text"],
                    google_review_time=r["google_review_time"],
                    review_likes=r.get("likes", 0),
                    source_platform="Google",
                    # Dashboard Metrics
                    is_praise=True if r["rating"] >= 4 else False,
                    is_complaint=True if r["rating"] <= 2 else False,
                    first_seen_at=datetime.utcnow(),
                    last_updated_at=datetime.utcnow()
                ).on_conflict_do_nothing(index_elements=['google_review_id'])
                
                result = await db.execute(stmt)
                if result.rowcount > 0:
                    new_count += 1

        logger.info(f"✅ SUCCESS: {new_count} new reviews saved to Postgres.")
        
        return {
            "status": "success",
            "fetched": len(data),
            "newly_saved": new_count,
            "message": f"Successfully ingested {new_count} reviews."
        }

    except Exception as e:
        logger.error(f"❌ DATABASE ERROR: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/check_db/{company_id}")
async def check_db(company_id: int, db: AsyncSession = Depends(get_session)):
    """Helper to verify if data is actually there."""
    res = await db.execute(select(func.count(Review.id)).where(Review.company_id == company_id))
    return {"total_records_in_postgres": res.scalar()}
