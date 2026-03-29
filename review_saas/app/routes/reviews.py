import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.core.database import get_db
from app.core.models import Review, Company
from app.services.review import sync_reviews_for_company

# Initialize the router that app/main.py is searching for
router = APIRouter()
logger = logging.getLogger("app.routes.reviews")

@router.get("/reviews", response_model=Dict[str, Any])
async def get_all_reviews(
    company_id: Optional[int] = None,
    limit: int = Query(10, ge=1, le=100),
    offset: int = 0,
    db: AsyncSession = Depends(get_db)
):
    """
    Retrieves reviews from the database with optional filtering by company.
    Used by the Chart.js frontend to populate the dashboard.
    """
    try:
        query = select(Review).order_by(desc(Review.created_at))
        
        if company_id:
            query = query.where(Review.company_id == company_id)
            
        result = await db.execute(query.offset(offset).limit(limit))
        reviews = result.scalars().all()
        
        # Format the response for the frontend table and charts
        return {
            "status": "success",
            "count": len(reviews),
            "data": [
                {
                    "id": r.id,
                    "author": r.author_name,
                    "rating": r.rating,
                    "text": r.text,
                    "sentiment": r.sentiment_score,
                    "date": r.created_at.isoformat() if r.created_at else None,
                    "google_id": r.google_review_id
                } for r in reviews
            ]
        }
    except Exception as e:
        logger.error(f"Error fetching reviews: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error while fetching reviews")

@router.post("/reviews/sync/{company_id}")
async def sync_reviews(
    company_id: int, 
    limit: int = 100, 
    db: AsyncSession = Depends(get_db)
):
    """
    Trigger point for the Scraper service to fetch new data from SerpApi,
    calculate sentiment, and save to the database.
    """
    # Verify company existence before proceeding
    company_res = await db.execute(select(Company).where(Company.id == company_id))
    company = company_res.scalar_one_or_none()
    
    if not company:
        raise HTTPException(status_code=404, detail=f"Company with ID {company_id} not found")

    # Call the service layer orchestration
    result = await sync_reviews_for_company(db, company_id, target_limit=limit)
    
    if result["status"] == "error":
        raise HTTPException(status_code=500, detail=result["message"])
        
    return result

@router.get("/reviews/stats/{company_id}")
async def get_review_stats(company_id: int, db: AsyncSession = Depends(get_db)):
    """
    Provides aggregated metrics (Avg Rating, Sentiment Distribution) 
    specifically for the Dashboard KPI cards.
    """
    result = await db.execute(select(Review).where(Review.company_id == company_id))
    reviews = result.scalars().all()
    
    if not reviews:
        return {
            "total_reviews": 0,
            "average_rating": 0,
            "sentiment_summary": {"positive": 0, "neutral": 0, "negative": 0}
        }

    pos = len([r for r in reviews if r.sentiment_score > 0.1])
    neu = len([r for r in reviews if -0.1 <= r.sentiment_score <= 0.1])
    neg = len([r for r in reviews if r.sentiment_score < -0.1])

    return {
        "total_reviews": len(reviews),
        "average_rating": round(sum(r.rating for r in reviews) / len(reviews), 2),
        "sentiment_summary": {
            "positive": pos,
            "neutral": neu,
            "negative": neg
        }
    }
