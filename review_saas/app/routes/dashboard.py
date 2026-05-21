# ==========================================================
# FILE: app/routes/dashboard.py
# TRUSTLYTICS AI — FINAL ENTERPRISE DASHBOARD ROUTER
# FIXES:
# ✅ Review API failed
# ✅ PostgreSQL review loading
# ✅ Dashboard analytics
# ✅ Timeline filtering
# ✅ ReviewService import issue
# ✅ Missing get_latest_reviews
# ✅ Dashboard charts
# ✅ Railway production stability
# ==========================================================

from fastapi import (
    APIRouter,
    HTTPException,
    Query,
    Request,
)

from pydantic import BaseModel

from typing import (
    Dict,
    Any,
    List
)

import logging
import statistics

from datetime import (
    datetime,
    timedelta,
)

from collections import (
    Counter,
    defaultdict,
)

from sqlalchemy import (
    select,
    desc
)

# ==========================================================
# DATABASE
# ==========================================================

from app.core.db import (
    AsyncSessionLocal
)

# ==========================================================
# MODELS
# ==========================================================

from app.core.models import (
    Review
)

# ==========================================================
# LOGGER
# ==========================================================

logger = logging.getLogger(
    __name__
)

# ==========================================================
# ROUTER
# ==========================================================

router = APIRouter(
    tags=["dashboard"]
)

# ==========================================================
# REQUEST MODEL
# ==========================================================

class ChatRequest(BaseModel):

    message: str

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

# ==========================================================
# SAFE HELPERS
# ==========================================================

def safe_rating(review):

    try:

        if isinstance(review, dict):

            return int(
                review.get(
                    "rating",
                    0
                )
            )

        return int(
            getattr(
                review,
                "rating",
                0
            )
        )

    except:
        return 0

def safe_get(

    review,

    field,

    default=None
):

    try:

        if isinstance(review, dict):

            return review.get(
                field,
                default
            )

        return getattr(
            review,
            field,
            default
        )

    except:
        return default

def calculate_sentiment(
    avg_rating: float
):

    if avg_rating >= 4:
        return "Positive"

    elif avg_rating >= 3:
        return "Neutral"

    return "Negative"

# ==========================================================
# GET REVIEWS FROM POSTGRESQL
# THIS FIXES:
# ❌ Review API failed
# ==========================================================

async def get_reviews_from_db(

    company_id: int,

    limit: int = 1000
):

    async with AsyncSessionLocal() as db:

        stmt = (

            select(Review)

            .where(
                Review.company_id == company_id
            )

            .order_by(
                desc(Review.created_at)
            )

            .limit(limit)
        )

        result = await db.execute(
            stmt
        )

        reviews = result.scalars().all()

        return reviews

# ==========================================================
# MAIN DASHBOARD API
# ==========================================================

@router.get("/dashboard/{company_id}")

async def get_dashboard_data(

    request: Request,

    company_id: int,

    days: int = Query(365)
):

    try:

        # ==================================================
        # LOAD REVIEWS DIRECTLY FROM POSTGRESQL
        # ==================================================

        reviews = await get_reviews_from_db(

            company_id=company_id,

            limit=1000
        )

        logger.info(
            f"✅ REVIEWS LOADED => {len(reviews)}"
        )

        # ==================================================
        # TIMELINE FILTERING
        # ==================================================

        now = datetime.utcnow()

        if days == 99999:

            start_date = datetime(
                2000,
                1,
                1
            )

        else:

            start_date = now - timedelta(
                days=days
            )

        filtered_reviews = []

        for review in reviews:

            try:

                created_at = safe_get(
                    review,
                    "created_at"
                )

                if not created_at:
                    continue

                if isinstance(
                    created_at,
                    str
                ):

                    review_date = datetime.fromisoformat(

                        created_at.replace(
                            "Z",
                            "+00:00"
                        )
                    )

                else:

                    review_date = created_at

                if review_date.tzinfo:

                    review_date = review_date.replace(
                        tzinfo=None
                    )

                if review_date >= start_date:

                    filtered_reviews.append(
                        review
                    )

            except Exception as e:

                logger.warning(
                    f"Timeline filtering failed => {e}"
                )

        reviews = filtered_reviews

        logger.info(
            f"📊 FILTERED REVIEWS => {len(reviews)}"
        )

        # ==================================================
        # KPI CALCULATIONS
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
            # MONTHLY GROUPING
            # ==============================================

            try:

                created_at = safe_get(
                    review,
                    "created_at"
                )

                if created_at:

                    if isinstance(
                        created_at,
                        str
                    ):

                        dt = datetime.fromisoformat(
                            str(created_at)
                        )

                    else:

                        dt = created_at

                    month_key = dt.strftime(
                        "%Y-%m"
                    )

                    monthly_reviews[
                        month_key
                    ] += 1

            except:
                pass

            # ==============================================
            # KEYWORD ANALYSIS
            # ==============================================

            text = str(

                safe_get(
                    review,
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
        # ADVANCED KPIs
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
                / max(1, total_reviews)
            ) * 100,

            2
        )

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
                total_reviews / 30
            ) * 10,

            2
        )

        growth_score = round(

            (
                positive_reviews
                - negative_reviews
            )

            / max(1, total_reviews)

            * 100,

            2
        )

        # ==================================================
        # RATING DISTRIBUTION
        # ==================================================

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

        sorted_months = sorted(
            monthly_reviews.items()
        )

        month_labels = [

            item[0]

            for item in sorted_months
        ]

        month_values = [

            item[1]

            for item in sorted_months
        ]

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
        # RESPONSE
        # ==================================================

        return {

            "status": "success",

            "company_id":
                company_id,

            "last_updated":
                datetime.utcnow().isoformat(),

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
                }
            },

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

        reviews = await get_reviews_from_db(

            company_id=company_id,

            limit=limit
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
                    safe_get(
                        review,
                        "author_name",
                        "Anonymous"
                    ),

                "rating":
                    rating,

                "review_text":
                    safe_get(
                        review,
                        "text",
                        ""
                    ),

                "created_at":
                    safe_get(
                        review,
                        "created_at",
                        "-"
                    ),

                "sentiment":
                    sentiment,

                "review_likes":
                    safe_get(
                        review,
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

        reviews = await get_reviews_from_db(

            company_id=company_id,

            limit=300
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
