from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel
from typing import Dict, Any
import logging
import statistics
from datetime import datetime
from collections import Counter

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api",
    tags=["dashboard"]
)

# ==========================================================
# SESSION AUTH
# ==========================================================

def get_current_user(request: Request):

    user = request.session.get("user")

    if not user:
        raise HTTPException(
            status_code=401,
            detail="Unauthorized"
        )

    return user

# ==========================================================
# REQUEST MODEL
# ==========================================================

class ChatRequest(BaseModel):
    message: str

# ==========================================================
# SAFE SERVICE IMPORTS
# ==========================================================

def get_company_service():
    try:
        from app.services.company_service import CompanyService
        return CompanyService
    except Exception as e:
        logger.exception("CompanyService import failed")
        raise HTTPException(
            status_code=500,
            detail=f"CompanyService error: {str(e)}"
        )

def get_review_service():
    try:
        try:
            from app.services.review_service import ReviewService
            return ReviewService
        except:
            from app.services.scraper import ReviewService
            return ReviewService

    except Exception as e:
        logger.exception("ReviewService import failed")
        raise HTTPException(
            status_code=500,
            detail=f"ReviewService error: {str(e)}"
        )

def get_insights_service():
    try:
        from app.services.ai_insights_service import AIInsightsService
        return AIInsightsService
    except Exception as e:
        logger.exception("InsightsService import failed")
        raise HTTPException(
            status_code=500,
            detail=f"InsightsService error: {str(e)}"
        )

# ==========================================================
# UTILITIES
# ==========================================================

def safe_rating(review):

    try:
        return int(review.get("rating", 0))
    except:
        return 0

def calculate_sentiment(avg_rating: float):

    if avg_rating >= 4:
        return "Positive"

    elif avg_rating >= 3:
        return "Neutral"

    return "Negative"

# ==========================================================
# GET COMPANIES
# FRONTEND API READY
# ==========================================================

@router.get("/companies")
async def get_companies(request: Request):

    user = get_current_user(request)

    try:

        CompanyService = get_company_service()

        companies = await CompanyService.get_user_companies(
            user["id"]
        )

        return {
            "status": "success",
            "companies": companies or []
        }

    except Exception as e:

        logger.exception("Companies load failed")

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

# ==========================================================
# ADD COMPANY
# ==========================================================

@router.post("/companies")
async def add_company(
    request: Request,
    payload: Dict[str, Any]
):

    user = get_current_user(request)

    try:

        if not payload.get("place_id"):

            raise HTTPException(
                status_code=400,
                detail="place_id is required"
            )

        CompanyService = get_company_service()

        company = await CompanyService.create_company(
            user_id=user["id"],
            name=payload.get("name"),
            place_id=payload.get("place_id"),
            address=payload.get("address")
        )

        return {
            "status": "success",
            "message": "Company added successfully",
            "company": company
        }

    except Exception as e:

        logger.exception("Add company failed")

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

# ==========================================================
# DASHBOARD DATA
# FRONTEND + DATABASE CONNECTED
# ==========================================================

@router.get("/dashboard/{company_id}")
async def get_dashboard_data(
    request: Request,
    company_id: int
):

    user = get_current_user(request)

    try:

        CompanyService = get_company_service()
        ReviewService = get_review_service()

        owns = await CompanyService.user_owns_company(
            user["id"],
            company_id
        )

        if not owns:

            raise HTTPException(
                status_code=403,
                detail="Access denied"
            )

        reviews = await ReviewService.get_latest_reviews(
            company_id,
            500
        )

        reviews = reviews or []

        total_reviews = len(reviews)

        ratings = [
            safe_rating(r)
            for r in reviews
            if safe_rating(r) > 0
        ]

        average_rating = round(
            statistics.mean(ratings),
            2
        ) if ratings else 0

        positive_reviews = len([
            r for r in reviews
            if safe_rating(r) >= 4
        ])

        negative_reviews = len([
            r for r in reviews
            if safe_rating(r) <= 2
        ])

        neutral_reviews = len([
            r for r in reviews
            if safe_rating(r) == 3
        ])

        reputation_score = round(
            (average_rating / 5) * 100,
            2
        )

        sentiment_score = round(
            (positive_reviews / total_reviews) * 100,
            2
        ) if total_reviews else 0

        revenue_risk = round(
            max(0, 100 - reputation_score),
            2
        )

        rating_counter = Counter(ratings)

        rating_distribution = [
            rating_counter.get(5, 0),
            rating_counter.get(4, 0),
            rating_counter.get(3, 0),
            rating_counter.get(2, 0),
            rating_counter.get(1, 0)
        ]

        return {
            "status": "success",
            "company_id": company_id,
            "total_reviews": total_reviews,
            "average_rating": average_rating,
            "positive_reviews": positive_reviews,
            "negative_reviews": negative_reviews,
            "neutral_reviews": neutral_reviews,
            "reputation_score": reputation_score,
            "revenue_risk": revenue_risk,
            "sentiment_score": sentiment_score,
            "customer_sentiment": calculate_sentiment(
                average_rating
            ),
            "rating_distribution": rating_distribution,
            "chart_labels": [
                "1 Star",
                "2 Star",
                "3 Star",
                "4 Star",
                "5 Star"
            ],
            "chart_values": rating_distribution,
            "last_updated": datetime.utcnow().isoformat()
        }

    except HTTPException:
        raise

    except Exception as e:

        logger.exception("Dashboard load failed")

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

# ==========================================================
# GET REVIEWS
# ==========================================================

@router.get("/reviews/company/{company_id}")
async def get_company_reviews(
    request: Request,
    company_id: int,
    limit: int = Query(100, le=500)
):

    user = get_current_user(request)

    try:

        CompanyService = get_company_service()
        ReviewService = get_review_service()

        owns = await CompanyService.user_owns_company(
            user["id"],
            company_id
        )

        if not owns:

            raise HTTPException(
                status_code=403,
                detail="Access denied"
            )

        reviews = await ReviewService.get_latest_reviews(
            company_id,
            limit
        )

        formatted_reviews = []

        for review in reviews:

            formatted_reviews.append({
                "author": review.get("author_name", "Anonymous"),
                "rating": review.get("rating", 0),
                "review_text": review.get("text")
                or review.get("review_text")
                or "",
                "created_at": review.get(
                    "relative_time_description"
                ) or review.get(
                    "created_at"
                ) or "-",
                "sentiment": calculate_sentiment(
                    review.get("rating", 0)
                )
            })

        return {
            "status": "success",
            "reviews": formatted_reviews
        }

    except Exception as e:

        logger.exception("Reviews load failed")

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

# ==========================================================
# INGEST GOOGLE REVIEWS
# ==========================================================

@router.post("/reviews/ingest/{company_id}")
async def ingest_reviews(
    request: Request,
    company_id: int
):

    user = get_current_user(request)

    try:

        CompanyService = get_company_service()
        ReviewService = get_review_service()

        owns = await CompanyService.user_owns_company(
            user["id"],
            company_id
        )

        if not owns:

            raise HTTPException(
                status_code=403,
                detail="Access denied"
            )

        result = await ReviewService.ingest_from_google(
            company_id
        )

        return {
            "status": "success",
            "message": "Reviews synced successfully",
            "reviews_collected": result.get(
                "ingested_count",
                0
            ),
            "synced_at": datetime.utcnow().isoformat()
        }

    except Exception as e:

        logger.exception("Review ingest failed")

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

# ==========================================================
# AI INSIGHTS
# ==========================================================

@router.get("/dashboard/ai-insights/{company_id}")
async def ai_insights(
    request: Request,
    company_id: int
):

    user = get_current_user(request)

    try:

        CompanyService = get_company_service()
        InsightsService = get_insights_service()

        owns = await CompanyService.user_owns_company(
            user["id"],
            company_id
        )

        if not owns:

            raise HTTPException(
                status_code=403,
                detail="Access denied"
            )

        insights = await InsightsService.generate_insights(
            company_id=company_id,
            start_date=None,
            end_date=None
        )

        return {
            "status": "success",
            "insights": insights,
            "generated_at": datetime.utcnow().isoformat()
        }

    except Exception as e:

        logger.exception("AI insights failed")

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

# ==========================================================
# AI CHAT
# ==========================================================

@router.post("/dashboard/chat/{company_id}")
async def dashboard_ai_chat(
    request: Request,
    company_id: int,
    payload: ChatRequest
):

    user = get_current_user(request)

    try:

        CompanyService = get_company_service()
        ReviewService = get_review_service()

        owns = await CompanyService.user_owns_company(
            user["id"],
            company_id
        )

        if not owns:

            raise HTTPException(
                status_code=403,
                detail="Access denied"
            )

        reviews = await ReviewService.get_latest_reviews(
            company_id,
            100
        )

        ratings = [
            safe_rating(r)
            for r in reviews
            if safe_rating(r) > 0
        ]

        avg_rating = round(
            statistics.mean(ratings),
            2
        ) if ratings else 0

        return {
            "status": "success",
            "chatbot": {
                "question": payload.message,
                "average_rating": avg_rating,
                "customer_sentiment": calculate_sentiment(
                    avg_rating
                ),
                "business_health_score": round(
                    (avg_rating / 5) * 100,
                    2
                ),
                "recommendations": [
                    "Reply quickly to negative reviews",
                    "Encourage happy customers to review",
                    "Monitor review sentiment weekly",
                    "Track repeated complaints",
                    "Improve customer response time"
                ],
                "generated_at": datetime.utcnow().isoformat()
            }
        }

    except Exception as e:

        logger.exception("AI chat failed")

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

# ==========================================================
# LOGOUT
# ==========================================================

@router.get("/auth/logout")
async def logout(request: Request):

    request.session.clear()

    return {
        "status": "success",
        "message": "Logged out successfully"
    }
