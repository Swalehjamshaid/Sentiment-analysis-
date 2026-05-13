from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel
from typing import Dict, Any
import logging
import statistics
from datetime import datetime
from collections import Counter

logger = logging.getLogger(__name__)

router = APIRouter(
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
# IMPORT SERVICES
# ==========================================================

def get_review_service():

    from app.services.scraper import ReviewService

    return ReviewService

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
# DASHBOARD DATA
# ==========================================================

@router.get("/dashboard/{company_id}")

async def get_dashboard_data(

    request: Request,

    company_id: int
):

    try:

        ReviewService = get_review_service()

        reviews = await ReviewService.get_latest_reviews(
            company_id,
            500
        )

        reviews = reviews or []

        total_reviews = len(reviews)

        ratings = []

        for review in reviews:

            rating = safe_rating(review)

            if rating > 0:
                ratings.append(rating)

        average_rating = round(
            statistics.mean(ratings),
            2
        ) if ratings else 0

        positive_reviews = len([
            r for r in ratings if r >= 4
        ])

        neutral_reviews = len([
            r for r in ratings if r == 3
        ])

        negative_reviews = len([
            r for r in ratings if r <= 2
        ])

        reputation_score = round(
            (average_rating / 5) * 100,
            2
        ) if average_rating else 0

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

            "customer_sentiment":
                calculate_sentiment(
                    average_rating
                ),

            "rating_distribution":
                rating_distribution,

            "chart_labels": [
                "5 Star",
                "4 Star",
                "3 Star",
                "2 Star",
                "1 Star"
            ],

            "chart_values":
                rating_distribution,

            "last_updated":
                datetime.utcnow().isoformat()
        }

    except Exception as e:

        logger.exception(
            "Dashboard API failed"
        )

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

    try:

        ReviewService = get_review_service()

        reviews = await ReviewService.get_latest_reviews(
            company_id,
            limit
        )

        formatted = []

        for review in reviews:

            formatted.append({

                "author":
                    review.get(
                        "author_name",
                        "Anonymous"
                    ),

                "rating":
                    review.get(
                        "rating",
                        0
                    ),

                "review_text":
                    review.get(
                        "text",
                        ""
                    ),

                "created_at":
                    review.get(
                        "created_at",
                        "-"
                    )
            })

        return {

            "status": "success",

            "reviews": formatted
        }

    except Exception as e:

        logger.exception(
            "Review API failed"
        )

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )
