from fastapi import APIRouter, Depends, HTTPException, Query, Body
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Dict, Optional, Any
import datetime
import logging

logger = logging.getLogger(__name__)

# ====================== Lazy Imports to Avoid Circular / Bootstrap Issues ======================
def get_company_service():
    from app.services.company_service import CompanyService
    return CompanyService

def get_review_service():
    from app.services.review_service import ReviewService
    return ReviewService

def get_ai_insights_service():
    from app.services.ai_insights_service import AIInsightsService
    return AIInsightsService

def get_revenue_risk_service():
    from app.services.revenue_risk_service import RevenueRiskService
    return RevenueRiskService

def get_ai_chat_service():
    from app.services.chat_service import AIChatService
    return AIChatService

# ====================== Pydantic Models ======================

class Company(BaseModel):
    id: int
    name: str
    business_name: Optional[str] = None
    place_id: str
    address: Optional[str] = None

class Review(BaseModel):
    id: Optional[int] = None
    rating: Optional[int] = None
    sentiment: Optional[str] = None
    review_text: Optional[str] = None
    review_date: Optional[datetime.datetime] = None
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

# ====================== Router ======================

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/companies")
async def get_companies(user=Depends(get_current_user)):   # Replace with your actual auth dependency
    """Return all companies linked by the current user"""
    try:
        CompanyService = get_company_service()
        companies = await CompanyService.get_user_companies(user.id)
        return {"companies": companies}
    except Exception as e:
        logger.error(f"Error fetching companies: {e}")
        raise HTTPException(status_code=500, detail="Failed to load companies")


@router.post("/companies")
async def add_company(payload: Dict[str, Any], user=Depends(get_current_user)):
    """Add new business via Google Place ID"""
    if not payload.get("place_id"):
        raise HTTPException(status_code=400, detail="place_id is required")

    try:
        CompanyService = get_company_service()
        company = await CompanyService.create_company(
            user_id=user.id,
            name=payload.get("name"),
            place_id=payload.get("place_id"),
            address=payload.get("address")
        )
        return {"message": "Business linked successfully", "company": company}
    except Exception as e:
        logger.error(f"Error adding company: {e}")
        raise HTTPException(status_code=500, detail="Failed to add business")


@router.get("/dashboard/ai/insights")
async def get_ai_insights(
    company_id: int = Query(..., gt=0),
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    user=Depends(get_current_user)
):
    """Main AI insights for dashboard (Analyze Business)"""
    try:
        # Optional: Add ownership check
        CompanyService = get_company_service()
        if not await CompanyService.user_owns_company(user.id, company_id):
            raise HTTPException(status_code=403, detail="Access denied to this business")

        AIInsightsService = get_ai_insights_service()
        insights = await AIInsightsService.generate_insights(
            company_id=company_id,
            start_date=start,
            end_date=end
        )
        return insights
    except Exception as e:
        logger.error(f"Insights generation failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate insights")


@router.get("/dashboard/latest-reviews")
async def get_latest_reviews(
    company_id: int = Query(...),
    limit: int = Query(100, le=500),
    user=Depends(get_current_user)
):
    """Latest reviews for the data table"""
    try:
        CompanyService = get_company_service()
        if not await CompanyService.user_owns_company(user.id, company_id):
            raise HTTPException(status_code=403, detail="Access denied")

        ReviewService = get_review_service()
        reviews = await ReviewService.get_latest_reviews(company_id, limit=limit)
        return reviews
    except Exception as e:
        logger.error(f"Failed to load latest reviews: {e}")
        raise HTTPException(status_code=500, detail="Failed to load reviews")


@router.get("/dashboard/revenue")
async def get_revenue_risk(
    company_id: int = Query(...),
    user=Depends(get_current_user)
):
    """Revenue risk monitoring"""
    try:
        CompanyService = get_company_service()
        if not await CompanyService.user_owns_company(user.id, company_id):
            raise HTTPException(status_code=403, detail="Access denied")

        RevenueRiskService = get_revenue_risk_service()
        risk_data = await RevenueRiskService.calculate_risk(company_id)
        return risk_data
    except Exception as e:
        logger.error(f"Revenue risk calculation failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to calculate risk")


@router.post("/reviews/ingest/{company_id}")
async def sync_live_reviews(company_id: int, user=Depends(get_current_user)):
    """Sync latest reviews from Google"""
    try:
        CompanyService = get_company_service()
        if not await CompanyService.user_owns_company(user.id, company_id):
            raise HTTPException(status_code=403, detail="Access denied")

        ReviewService = get_review_service()
        result = await ReviewService.ingest_from_google(company_id)

        return {
            "message": "Sync completed successfully",
            "reviews_count": result.get("ingested_count", 0),
            "new_reviews": result.get("new_reviews", 0)
        }
    except Exception as e:
        logger.error(f"Sync failed: {e}")
        raise HTTPException(status_code=500, detail="Sync operation failed")


@router.post("/dashboard/chat")
async def ai_chat(
    company_id: int = Query(...),
    request: ChatRequest = Body(...),
    user=Depends(get_current_user)
):
    """AI Strategy Consultant Chat"""
    try:
        CompanyService = get_company_service()
        if not await CompanyService.user_owns_company(user.id, company_id):
            raise HTTPException(status_code=403, detail="Access denied")

        AIChatService = get_ai_chat_service()
        answer = await AIChatService.get_response(
            company_id=company_id,
            user_message=request.message
        )
        return {"answer": answer}
    except Exception as e:
        logger.error(f"AI Chat failed: {e}")
        raise HTTPException(status_code=500, detail="AI service temporarily unavailable")


@router.get("/auth/logout")
async def logout(user=Depends(get_current_user)):
    """Simple logout endpoint"""
    # Add your logout logic here (clear token/session)
    return {"message": "Logged out successfully"}
