import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Project internal imports
from app.core.db import get_session
from app.core.models import Review, Company
# Ensure this import matches your file structure
from app.services.scraper import fetch_reviews_from_google 

router = APIRouter()
logger = logging.getLogger("app.routes.reviews")

@router.post("/reviews/ingest/{company_id}")
async def ingest_reviews(
    company_id: int, 
    db: AsyncSession = Depends(get_session)
):
    """Triggered by 'Sync Live Data' button. Handles fetching and saving to DB."""
    logger.info(f"🚀 Sync requested for company_id: {company_id}")
    
    try:
        # 1. Verify Company and get Google Place ID
        res = await db.execute(select(Company).where(Company.id == company_id))
        company = res.scalar_one_or_none()
        
        if not company or not company.google_place_id:
            logger.error(f"❌ Company {company_id} not found or missing Google Place ID")
            raise HTTPException(status_code=404, detail="Company or Place ID not found")

        # 2. Fetch raw data from the scraper 
        # Pass the company_id and session so the scraper can calculate the 'Offset'
        scraped_reviews = await fetch_reviews_from_google(
            place_id=company.google_place_id,
            company_id=company_id,
            session=db
        )
        
        if not scraped_reviews:
            logger.info(f"ℹ️ No new reviews found for company {company_id}")
            return {"status": "success", "reviews_collected": 0}

        new_entries = 0
        allowed_cols = Review.__table__.columns.keys()

        for r_data in scraped_reviews:
            # --- ATTRIBUTE MAPPING ---
            # Scraper uses 'google_review_time', DB model uses 'first_seen_at'
            if 'google_review_time' in r_data:
                r_data['first_seen_at'] = r_data.pop('google_review_time')
            
            # --- DYNAMIC FILTERING ---
            # Remove any keys the scraper provides that aren't in your DB table
            filtered_data = {k: v for k, v in r_data.items() if k in allowed_cols}

            # --- DUPLICATE PREVENTION ---
            # Double check against the DB before adding
            stmt = select(Review).where(
                Review.company_id == company_id,
                Review.google_review_id == filtered_data.get('google_review_id')
            )
            existing = await db.execute(stmt)
            
            if not existing.scalar_one_or_none():
                new_review = Review(company_id=company_id, **filtered_data)
                db.add(new_review)
                new_entries += 1
        
        # 3. Commit all new entries at once
        if new_entries > 0:
            await db.commit()
            logger.info(f"✅ Sync complete for ID {company_id} | Added: {new_entries}")
        else:
            logger.info(f"ℹ️ All fetched reviews were already present in DB for ID {company_id}")

        return {"status": "success", "reviews_collected": new_entries}

    except Exception as e:
        await db.rollback()
        logger.error(f"❌ Sync failed for ID {company_id}: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/ai/insights")
async def ai_insights(
    company_id: int, 
    start: str, 
    end: str, 
    db: AsyncSession = Depends(get_session)
):
    """Provides statistics for the dashboard charts."""
    try:
        # Handle date formatting from frontend
        start_dt = datetime.fromisoformat(start.replace('Z', '+00:00'))
        end_dt = datetime.fromisoformat(end.replace('Z', '+00:00'))

        query = select(Review).where(
            Review.company_id == company_id,
            Review.first_seen_at >= start_dt,
            Review.first_seen_at <= end_dt
        )
        
        result = await db.execute(query)
        reviews = result.scalars().all()
        
        total = len(reviews)
        avg_score = sum(r.rating for r in reviews if r.rating) / total if total > 0 else 0
        
        return {
            "total_reviews": total,
            "average_rating": round(avg_score, 2),
            "status": "success",
            "period": {"start": start, "end": end}
        }
    except Exception as e:
        logger.error(f"❌ Insight generation failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal Server Error")
