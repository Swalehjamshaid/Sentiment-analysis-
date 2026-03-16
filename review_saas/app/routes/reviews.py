# filename: app/routes/reviews.py

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Dict

from app.core.db import get_session
from app.core.models import Company
from app.services.review import sync_all_companies_with_google, add_review

# -------------------------------
# Create Router
# -------------------------------
router = APIRouter()

# -------------------------------
# Test route
# -------------------------------
@router.get("/test")
async def test_reviews():
    return {"status": "reviews router working"}

# -------------------------------
# Get all companies
# -------------------------------
@router.get("/companies", response_model=List[Dict])
async def get_companies(session: AsyncSession = Depends(get_session)):
    """
    Returns all companies with full details.
    """
    result = await session.execute(
        """SELECT id, name, address, latitude, longitude, phone, website, rating, reviews_count, is_active 
           FROM companies"""
    )
    companies = result.all()
    return [dict(row._mapping) for row in companies]

# -------------------------------
# Sync all inactive companies with Google
# -------------------------------
@router.post("/sync-google")
async def sync_companies():
    """
    Syncs all inactive companies with Google API and updates database.
    """
    await sync_all_companies_with_google()
    return {"status": "All inactive companies synced with Google API."}

# -------------------------------
# Add a new review for a company
# -------------------------------
@router.post("/companies/{company_id}/reviews")
async def create_review(
    company_id: int,
    author_name: str,
    text: str,
    rating: float,
    session: AsyncSession = Depends(get_session),
):
    """
    Adds a new review for the specified company.
    """
    company = await session.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    
    review = await add_review(company_id, author_name, text, rating, session)
    return {
        "status": "Review added",
        "review_id": review.id,
        "company_id": company_id,
    }
