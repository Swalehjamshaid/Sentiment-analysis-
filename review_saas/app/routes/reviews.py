import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

# Project internal imports
from app.core.db import get_session
from app.services.review import sync_reviews_for_company, get_dashboard_insights

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
    
    # Calls the logic in your services/review.py
    result = await sync_reviews_for_company(db, company_id)
    
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("message"))
        
    return result

@router.get("/ai/insights")
async def ai_insights(
    company_id: int, 
    start: str, 
    end: str, 
    db: AsyncSession = Depends(get_session)
):
    """Provides data for the dashboard charts."""
    try:
        return await get_dashboard_insights(db, company_id, start, end)
    except Exception as e:
        logger.error(f"Insight generation failed: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")
