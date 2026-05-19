# filename: app/routes/dashboard.py

from fastapi import (
    APIRouter,
    HTTPException,
    Query,
    Request,
)

from pydantic import BaseModel

from typing import Dict, Any, List

import logging
import statistics
import math

from datetime import (
    datetime,
    timedelta,
)

from collections import (
    Counter,
    defaultdict,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["dashboard"]
)

# ==========================================================
# SESSION AUTH
# ==========================================================

def get_current_user(
    request: Request
):

    user_id = request.session.get(
        "user_id"
    )

    if not user_id:

        raise HTTPException(
            status_code=401,
            detail="Unauthorized"
        )

    return {

        "id":
            request.session.get(
                "user_id"
            ),

        "name":
            request.session.get(
                "user_name"
            ),

        "email":
            request.session.get(
                "user_email"
            )
    }
# ==========================================================
# REQUEST MODEL
# ==========================================================

class ChatRequest(BaseModel):

    message: str

# ==========================================================
# IMPORT SERVICES
# ==========================================================

def get_review_service():

    from app.services.scraper import (
        ReviewService
    )

    return ReviewService

# ==========================================================
# UTILITIES
# ==========================================================

POSITIVE_WORDS = [

    "good",
    "great",
    "excellent",
    "amazing",
    "fast",
    "nice",
    "best",
    "love",
    "awesome",
    "perfect",
]

NEGATIVE_WORDS = [

    "bad",
    "slow",
    "poor",
    "worst",
    "delay",
    "issue",
    "problem",
    "damage",
    "broken",
    "late",
]

def safe_rating(review):

    try:
        return int(
            review.get(
                "rating",
                0
            )
        )
    except:
        return 0

def calculate_sentiment(
    avg_rating: float
):

    if avg_rating >= 4:
        return "Positive"

    elif avg_rating >= 3:
        return "Neutral"

    return "Negative"

def month_name(date_obj):

    try:
        return date_obj.strftime("%b")
    except:
        return "Unknown"

# ==========================================================
# MAIN DASHBOARD
# ==========================================================

@router.get("/dashboard/{company_id}")

async def get_dashboard_data(

    request: Request,

    company_id: int
):

    try:

        ReviewService = get_review_service()

        from app.core.db import AsyncSessionLocal

        async with AsyncSessionLocal() as db:

            reviews = await ReviewService.get_latest_reviews(

                db=db,

                company_id=company_id,

                limit=1000
            )

        reviews = reviews or []

        # ==================================================
        # BASIC KPIs
        # ==================================================

        total_reviews = len(reviews)

        ratings = []

        positive_reviews = 0
        neutral_reviews = 0
        negative_reviews = 0

        monthly_reviews = defaultdict(int)

        keyword_counter = Counter()

        for review in reviews:

            rating = safe_rating(review)

            if rating > 0:

                ratings.append(rating)

                if rating >= 4:
                    positive_reviews += 1

                elif rating == 3:
                    neutral_reviews += 1

                else:
                    negative_reviews += 1

            # ==============================================
            # MONTHLY TREND
            # ==============================================

            try:

                created_at = review.get(
                    "created_at"
                )

                if created_at:

                    dt = datetime.fromisoformat(
                        str(created_at)
                    )

                    monthly_reviews[
                        month_name(dt)
                    ] += 1

            except:
                pass

            # ==============================================
            # KEYWORD ANALYSIS
            # ==============================================

            text = str(
                review.get(
                    "text",
                    ""
                )
            ).lower()

            for word in POSITIVE_WORDS:

                if word in text:

                    keyword_counter[word] += 1

            for word in NEGATIVE_WORDS:

                if word in text:

                    keyword_counter[word] += 1

        # ==================================================
        # ADVANCED ANALYTICS
        # ==================================================

        average_rating = round(
            statistics.mean(ratings),
            2
        ) if ratings else 0

        reputation_score = round(
            (average_rating / 5) * 100,
            2
        ) if average_rating else 0

        customer_satisfaction = round(
            (
                positive_reviews
                / total_reviews
            ) * 100,
            2
        ) if total_reviews else 0

        revenue_risk = round(
            max(
                0,
                100 - reputation_score
            ),
            2
        )

        customer_retention = round(
            min(
                100,
                reputation_score * 0.92
            ),
            2
        )

        engagement_rate = round(
            (
                total_reviews
                / max(1, 30)
            ) * 10,
            2
        )

        growth_score = round(
            (
                positive_reviews
                - negative_reviews
            ) / max(
                1,
                total_reviews
            ) * 100,
            2
        )

        rating_counter = Counter(
            ratings
        )

        rating_distribution = [

            rating_counter.get(5, 0),

            rating_counter.get(4, 0),

            rating_counter.get(3, 0),

            rating_counter.get(2, 0),

            rating_counter.get(1, 0)
        ]

        # ==================================================
        # MONTHLY TREND
        # ==================================================

        month_labels = list(
            monthly_reviews.keys()
        )

        month_values = list(
            monthly_reviews.values()
        )

        # ==================================================
        # TOP KEYWORDS
        # ==================================================

        top_keywords = []

        for word, count in keyword_counter.most_common(10):

            top_keywords.append({

                "keyword":
                    word,

                "count":
                    count
            })

        # ==================================================
        # STAR PERCENTAGES
        # ==================================================

        star_percentages = []

        for star in [5, 4, 3, 2, 1]:

            value = rating_counter.get(star, 0)

            percent = round(
                (
                    value
                    / max(1, total_reviews)
                ) * 100,
                2
            )

            star_percentages.append({

                "star":
                    star,

                "count":
                    value,

                "percentage":
                    percent
            })

        # ==================================================
        # SENTIMENT BREAKDOWN
        # ==================================================

        sentiment_breakdown = {

            "positive":
                positive_reviews,

            "neutral":
                neutral_reviews,

            "negative":
                negative_reviews
        }

        # ==================================================
        # DASHBOARD RESPONSE
        # ==================================================

        return {

            "status": "success",

            "company_id":
                company_id,

            "last_updated":
                datetime.utcnow().isoformat(),

            # ==============================================
            # MAIN KPIs
            # ==============================================

            "kpis": {

                "total_reviews":
                    total_reviews,

                "average_rating":
                    average_rating,

                "reputation_score":
                    reputation_score,

                "customer_satisfaction":
                    customer_satisfaction,

                "customer_retention":
                    customer_retention,

                "engagement_rate":
                    engagement_rate,

                "growth_score":
                    growth_score,

                "revenue_risk":
                    revenue_risk,
            },

            # ==============================================
            # REVIEW BREAKDOWN
            # ==============================================

            "review_breakdown": {

                "positive_reviews":
                    positive_reviews,

                "neutral_reviews":
                    neutral_reviews,

                "negative_reviews":
                    negative_reviews,

                "customer_sentiment":
                    calculate_sentiment(
                        average_rating
                    ),
            },

            # ==============================================
            # CHARTS
            # ==============================================

            "charts": {

                "rating_distribution": {

                    "labels": [

                        "5 Star",
                        "4 Star",
                        "3 Star",
                        "2 Star",
                        "1 Star"
                    ],

                    "values":
                        rating_distribution
                },

                "monthly_trend": {

                    "labels":
                        month_labels,

                    "values":
                        month_values
                },

                "sentiment_breakdown":
                    sentiment_breakdown,

                "star_percentages":
                    star_percentages
            },

            # ==============================================
            # INSIGHTS
            # ==============================================

            "insights": {

                "top_keywords":
                    top_keywords,

                "risk_level":
                    (
                        "High"
                        if revenue_risk >= 70
                        else "Medium"
                        if revenue_risk >= 40
                        else "Low"
                    ),

                "performance":
                    (
                        "Excellent"
                        if average_rating >= 4.5
                        else "Good"
                        if average_rating >= 4
                        else "Average"
                        if average_rating >= 3
                        else "Poor"
                    ),
            }
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
# GET COMPANY REVIEWS
# ==========================================================

@router.get("/reviews/company/{company_id}")

async def get_company_reviews(

    request: Request,

    company_id: int,

    limit: int = Query(
        100,
        le=1000
    )
):

    try:

        ReviewService = get_review_service()

        reviews = await ReviewService.get_latest_reviews(
            company_id,
            limit
        )

        formatted = []

        for review in reviews:

            rating = safe_rating(review)

            sentiment = (

                "positive"

                if rating >= 4

                else "negative"

                if rating <= 2

                else "neutral"
            )

            formatted.append({

                "author":
                    review.get(
                        "author_name",
                        "Anonymous"
                    ),

                "rating":
                    rating,

                "review_text":
                    review.get(
                        "text",
                        ""
                    ),

                "created_at":
                    review.get(
                        "created_at",
                        "-"
                    ),

                "sentiment":
                    sentiment,

                "review_likes":
                    review.get(
                        "review_likes",
                        0
                    )
            })

        return {

            "status": "success",

            "total_reviews":
                len(formatted),

            "reviews":
                formatted
        }

    except Exception as e:

        logger.exception(
            "Review API failed"
        )

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

# ==========================================================
# AI CHAT ANALYSIS
# ==========================================================

@router.post("/dashboard/chat/{company_id}")

async def dashboard_chat(

    request: Request,

    company_id: int,

    payload: ChatRequest
):

    try:

        ReviewService = get_review_service()

        reviews = await ReviewService.get_latest_reviews(
            company_id,
            300
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

        recommendations = []

        if avg_rating < 3:

            recommendations.extend([

                "Improve customer response speed",

                "Reduce complaint resolution time",

                "Improve service quality",

                "Analyze negative review patterns"
            ])

        elif avg_rating < 4:

            recommendations.extend([

                "Increase customer engagement",

                "Focus on customer retention",

                "Improve review response quality"
            ])

        else:

            recommendations.extend([

                "Maintain service consistency",

                "Encourage more customer reviews",

                "Expand positive engagement"
            ])

        return {

            "status": "success",

            "question":
                payload.message,

            "analysis": {

                "average_rating":
                    avg_rating,

                "business_health":
                    round(
                        avg_rating * 20,
                        2
                    ),

                "customer_sentiment":
                    calculate_sentiment(
                        avg_rating
                    ),

                "recommendations":
                    recommendations
            }
        }

    except Exception as e:

        logger.exception(
            "Dashboard AI failed"
        )

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )
