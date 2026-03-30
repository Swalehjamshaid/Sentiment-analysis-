import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Project internal imports
from app.core.db import get_session
from app.core.models import Review, Company
# Ensure this import points to your actual scraping function
from app.services.scraper import fetch_reviews_from_google 

# --- CRITICAL FIX: main.py looks specifically for this 'router' variable ---
router = APIRouter()
logger = logging.getLogger("app.routes.reviews")

@router.post("/reviews/ingest/{company_id}")
async def ingest_reviews(
    company_id: int, 
    db: AsyncSession = Depends(get_session)
):
    """Triggered by 'Sync Live Data' button on the dashboard."""
    logger.info(f"🚀 Sync requested for company_id: {company_id}")
    
    try:
        # 1. Get the company to retrieve the Google Place ID
        res = await db.execute(select(Company).where(Company.id == company_id))
        company = res.scalar_one_or_none()
        
        if not company or not company.google_place_id:
            raise HTTPException(status_code=404, detail="Company or Place ID not found")

        # 2. Fetch raw data from the scraper
        scraped_reviews = await fetch_reviews_from_google(company.google_place_id)
        
        new_entries = 0
        for r_data in scraped_reviews:
            # --- THE KEY FIX ---
            # Map 'created_at' from scraper to 'first_seen_at' in your Review model
            if 'created_at' in r_data:
                r_data['first_seen_at'] = r_data.pop('created_at')
            
            # --- DYNAMIC FILTERING ---
            # Only keep keys that exist in your Review model's table columns
            # This prevents "invalid keyword argument" errors
            allowed_cols = Review.__table__.columns.keys()
            filtered_data = {k: v for k, v in r_data.items() if k in allowed_cols}

            # 3. Duplicate Prevention
            stmt = select(Review).where(
                Review.company_id == company_id,
                Review.google_review_id == filtered_data.get('google_review_id')
            )
            existing = await db.execute(stmt)
            
            if not existing.scalar_one_or_none():
                # Create the Review object using the mapped and filtered data
                db.add(Review(company_id=company_id, **filtered_data))
                new_entries += 1
        
        await db.commit()
        logger.info(f"✅ Sync complete for ID {company_id} | Added: {new_entries}")
        return {"status": "success", "reviews_collected": new_entries}

    except Exception as e:
        await db.rollback()
        logger.error(f"❌ Sync failed: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/ai/insights")
async def ai_insights(
    company_id: int, 
    start: str, 
    end: str, 
    db: AsyncSession = Depends(get_session)
):
    """Provides data for the dashboard charts using first_seen_at."""
    try:
        # Convert incoming strings to Python datetime objects
        start_dt = datetime.fromisoformat(start)
        end_dt = datetime.fromisoformat(end)

        # --- THE ATTRIBUTE FIX ---
        # Querying using 'first_seen_at' to match your models.py
        query = select(Review).where(
            Review.company_id == company_id,
            Review.first_seen_at >= start_dt,
            Review.first_seen_at <= end_dt
        )
        
        result = await db.execute(query)
        reviews = result.scalars().all()
        
        # Calculate stats for the dashboard output
        total = len(reviews)
        avg_score = sum(r.rating for r in reviews if r.rating) / total if total > 0 else 0
        
        return {
            "total_reviews": total,
            "average_rating": round(avg_score, 2),
            "status": "success"
        }
    except Exception as e:
        logger.error(f"❌ Insight generation failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal Server Error")
