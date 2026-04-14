from fastapi import APIRouter, Depends, HTTPException, Query, Body
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Dict, Optional, Any
import datetime

# Assuming you have these in your project
from ..dependencies import get_current_user  # or your auth dependency
from ..services.company_service import CompanyService
from ..services.review_service import ReviewService
from ..services.ai_insights_service import AIInsightsService
from ..services.revenue_risk_service import RevenueRiskService
from ..services.chat_service import AIChatService

router = APIRouter(prefix="/api", tags=["dashboard"])

# ====================== MODELS ======================

class Company(BaseModel):
    id: int
    name: str
    business_name: Optional[str] = None
    place_id: str
    address: Optional[str] = None

class Review(BaseModel):
    id: int
    rating: Optional[int]
    sentiment: Optional[str]
    review_text: Optional[str]
    review_date: Optional[datetime.datetime]
    source: str = "Google"

class InsightsResponse(BaseModel):
    metadata: Dict[str, Any]
    kpis: Dict[str, Any]
    visualizations: Dict[str, Any]

class RevenueRiskResponse(BaseModel):
    risk_percent: float
    impact: str
    details: Optional[Dict] = None

class ChatRequest(BaseModel):
    message: str

class ChatResponse(BaseModel):
    answer: str

# ====================== ROUTES ======================

@router.get("/companies")
async def get_companies(user = Depends(get_current_user)):
    """Return all companies linked by the current user"""
    companies = await CompanyService.get_user_companies(user.id)
    return {"companies": companies}


@router.post("/companies")
async def add_company(payload: Dict[str, Any], user = Depends(get_current_user)):
    """Add new business (Google Place)"""
    if not payload.get("place_id"):
        raise HTTPException(status_code=400, detail="place_id is required")

    company = await CompanyService.create_company(
        user_id=user.id,
        name=payload.get("name"),
        place_id=payload.get("place_id"),
        address=payload.get("address")
    )
    return {"message": "Business linked successfully", "company": company}


@router.get("/dashboard/ai/insights")
async def get_ai_insights(
    company_id: int = Query(..., description="Company ID"),
    start: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    user = Depends(get_current_user)
):
    """Main dashboard insights (called by Analyze Business button)"""
    # Verify user owns the company
    if not await CompanyService.user_owns_company(user.id, company_id):
        raise HTTPException(status_code=403, detail="Access denied")

    insights = await AIInsightsService.generate_insights(
        company_id=company_id,
        start_date=start,
        end_date=end
    )

    return insights


@router.get("/dashboard/latest-reviews")
async def get_latest_reviews(
    company_id: int = Query(...),
    limit: int = Query(100, le=500),
    user = Depends(get_current_user)
):
    """Latest reviews for the table"""
    if not await CompanyService.user_owns_company(user.id, company_id):
        raise HTTPException(status_code=403, detail="Access denied")

    reviews = await ReviewService.get_latest_reviews(company_id, limit=limit)
    return reviews


@router.get("/dashboard/revenue")
async def get_revenue_risk(
    company_id: int = Query(...),
    user = Depends(get_current_user)
):
    """Revenue risk monitoring"""
    if not await CompanyService.user_owns_company(user.id, company_id):
        raise HTTPException(status_code=403, detail="Access denied")

    risk_data = await RevenueRiskService.calculate_risk(company_id)
    return risk_data


@router.post("/reviews/ingest/{company_id}")
async def sync_live_reviews(company_id: int, user = Depends(get_current_user)):
    """Sync latest reviews from Google (called by Sync Live Data)"""
    if not await CompanyService.user_owns_company(user.id, company_id):
        raise HTTPException(status_code=403, detail="Access denied")

    result = await ReviewService.ingest_from_google(company_id)
    return {
        "message": "Sync completed",
        "reviews_count": result.get("ingested_count", 0),
        "new_reviews": result.get("new_reviews", 0)
    }


@router.post("/dashboard/chat")
async def ai_chat(
    company_id: int = Query(...),
    request: ChatRequest = Body(...),
    user = Depends(get_current_user)
):
    """AI Strategy Consultant Chat"""
    if not await CompanyService.user_owns_company(user.id, company_id):
        raise HTTPException(status_code=403, detail="Access denied")

    answer = await AIChatService.get_response(
        company_id=company_id,
        user_message=request.message
    )

    return {"answer": answer}


# Optional: Logout route (if you want to handle it server-side)
@router.get("/auth/logout")
async def logout(user = Depends(get_current_user)):
    # Implement your logout logic (clear session / token)
    return {"message": "Logged out successfully"}
