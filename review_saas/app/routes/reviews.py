import logging
from typing import Dict, Any, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.models import Review, Company
from app.services.review import sync_reviews_for_company, get_dashboard_insights, get_revenue_risk

# THIS IS THE CRITICAL LINE: main.py looks for this 'router' attribute
router = APIRouter()
logger = logging.getLogger("app.routes.reviews")

@router.post("/reviews/ingest/{company_id}")
async def ingest_reviews(company_id: int, db: AsyncSession = Depends(get_db)):
    """
    Triggered by the 'Sync Live Data' button in the HTML dashboard.
    """
    result = await sync_reviews_for_company(db, company_id)
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("message"))
    return result

@router.get("/ai/insights")
async def ai_insights(
    company_id: int, 
    start: str, 
    end: str, 
    db: AsyncSession = Depends(get_db)
):
    """
    Triggered by the 'Analyze Business' button. 
    Provides data for Radar, Line, and Bar charts.
    """
    try:
        return await get_dashboard_insights(db, company_id, start, end)
    except Exception as e:
        logger.error(f"Insight generation failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate AI insights")

@router.get("/dashboard/revenue")
async def dashboard_revenue(company_id: int, db: AsyncSession = Depends(get_db)):
    """
    Updates the 'Revenue Risk Monitoring' card in the HTML.
    """
    return await get_revenue_risk(db, company_id)

@router.get("/companies")
async def get_companies(db: AsyncSession = Depends(get_db)):
    """
    Populates the 'ACTIVE ENTITY' dropdown in the HTML.
    """
    result = await db.execute(select(Company))
    companies = result.scalars().all()
    return [{"id": c.id, "name": c.name} for c in companies]
