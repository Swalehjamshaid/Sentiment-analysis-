from fastapi import APIRouter, Depends, HTTPException, Query, Body
from pydantic import BaseModel
from typing import Dict, Optional, Any
import datetime
import logging

logger = logging.getLogger(__name__)

# Lazy service loading to reduce import-time errors
def get_service(name: str):
    try:
        if name == "company":
            from app.services.company_service import CompanyService
            return CompanyService
        elif name == "review":
            from app.services.review_service import ReviewService
            return ReviewService
        elif name == "insights":
            from app.services.ai_insights_service import AIInsightsService
            return AIInsightsService
        elif name == "revenue":
            from app.services.revenue_risk_service import RevenueRiskService
            return RevenueRiskService
        elif name == "chat":
            from app.services.chat_service import AIChatService
            return AIChatService
    except Exception as e:
        logger.error(f"Failed to import {name}_service: {e}")
        raise HTTPException(status_code=500, detail=f"Service {name} not available")
    raise HTTPException(status_code=500, detail="Unknown service")


router = APIRouter(prefix="/api", tags=["dashboard"])


class ChatRequest(BaseModel):
    message: str


@router.get("/companies")
async def get_companies(user=Depends(get_current_user)):
    try:
        CompanyService = get_service("company")
        companies = await CompanyService.get_user_companies(user.id)
        return {"companies": companies or []}
    except Exception as e:
        logger.exception("Error in get_companies")
        raise HTTPException(status_code=500, detail="Failed to load companies")


@router.post("/companies")
async def add_company(payload: Dict[str, Any], user=Depends(get_current_user)):
    if not payload.get("place_id"):
        raise HTTPException(status_code=400, detail="place_id is required")

    try:
        CompanyService = get_service("company")
        company = await CompanyService.create_company(
            user_id=user.id,
            name=payload.get("name"),
            place_id=payload.get("place_id"),
            address=payload.get("address")
        )
        return {"message": "Business linked successfully", "company": company}
    except Exception as e:
        logger.exception("Error adding company")
        raise HTTPException(status_code=500, detail="Failed to add business")


@router.get("/dashboard/ai/insights")
async def get_ai_insights(
    company_id: int = Query(..., gt=0),
    start: Optional[str] = None,
    end: Optional[str] = None,
    user=Depends(get_current_user)
):
    try:
        CompanyService = get_service("company")
        if not await CompanyService.user_owns_company(user.id, company_id):
            raise HTTPException(status_code=403, detail="Access denied")

        InsightsService = get_service("insights")
        insights = await InsightsService.generate_insights(
            company_id=company_id, start_date=start, end_date=end
        )
        return insights
    except Exception as e:
        logger.exception("Insights failed")
        raise HTTPException(status_code=500, detail="Failed to generate insights")


@router.get("/dashboard/latest-reviews")
async def get_latest_reviews(
    company_id: int = Query(...),
    limit: int = Query(100, le=500),
    user=Depends(get_current_user)
):
    try:
        CompanyService = get_service("company")
        if not await CompanyService.user_owns_company(user.id, company_id):
            raise HTTPException(status_code=403, detail="Access denied")

        ReviewService = get_service("review")
        reviews = await ReviewService.get_latest_reviews(company_id, limit)
        return reviews
    except Exception as e:
        logger.exception("Latest reviews failed")
        raise HTTPException(status_code=500, detail="Failed to load reviews")


@router.get("/dashboard/revenue")
async def get_revenue_risk(company_id: int = Query(...), user=Depends(get_current_user)):
    try:
        CompanyService = get_service("company")
        if not await CompanyService.user_owns_company(user.id, company_id):
            raise HTTPException(status_code=403, detail="Access denied")

        RevenueService = get_service("revenue")
        return await RevenueService.calculate_risk(company_id)
    except Exception as e:
        logger.exception("Revenue risk failed")
        raise HTTPException(status_code=500, detail="Failed to calculate risk")


@router.post("/reviews/ingest/{company_id}")
async def sync_live_reviews(company_id: int, user=Depends(get_current_user)):
    try:
        CompanyService = get_service("company")
        if not await CompanyService.user_owns_company(user.id, company_id):
            raise HTTPException(status_code=403, detail="Access denied")

        ReviewService = get_service("review")
        result = await ReviewService.ingest_from_google(company_id)
        return {
            "message": "Sync completed",
            "reviews_count": result.get("ingested_count", 0)
        }
    except Exception as e:
        logger.exception("Sync failed")
        raise HTTPException(status_code=500, detail="Sync failed")


@router.post("/dashboard/chat")
async def ai_chat(
    company_id: int = Query(...),
    request: ChatRequest = Body(...),
    user=Depends(get_current_user)
):
    try:
        CompanyService = get_service("company")
        if not await CompanyService.user_owns_company(user.id, company_id):
            raise HTTPException(status_code=403, detail="Access denied")

        ChatService = get_service("chat")
        answer = await ChatService.get_response(company_id, request.message)
        return {"answer": answer}
    except Exception as e:
        logger.exception("Chat failed")
        raise HTTPException(status_code=500, detail="AI chat unavailable")


@router.get("/auth/logout")
async def logout(user=Depends(get_current_user)):
    return {"message": "Logged out"}
