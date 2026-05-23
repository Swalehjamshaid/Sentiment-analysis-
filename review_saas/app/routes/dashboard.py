# ==========================================================
# FILE: app/routes/dashboard.py
# REVIEW INTEL AI — ENTERPRISE EXECUTIVE VERSION
# FULLY COMPATIBLE WITH dashboard.html
# ==========================================================

from fastapi import (
    APIRouter,
    HTTPException,
    Query,
    Request
)

from pydantic import BaseModel

from collections import (
    Counter,
    defaultdict
)

from sqlalchemy import (
    select,
    desc
)

from datetime import (
    datetime,
    timedelta
)

import statistics
import logging

# ==========================================================
# DATABASE
# ==========================================================

from app.core.db import AsyncSessionLocal

# ==========================================================
# MODELS
# ==========================================================

from app.core.models import Review

# ==========================================================
# LOGGER
# ==========================================================

logger = logging.getLogger(__name__)

# ==========================================================
# ROUTER
# ==========================================================

router = APIRouter(
    tags=["Dashboard"]
)

# ==========================================================
# CHAT MODEL
# ==========================================================

class ChatRequest(BaseModel):
    message: str

# ==========================================================
# SAFE HELPERS
# ==========================================================

def safe_rating(review):

    try:

        rating = getattr(review, "rating", 0)

        if rating is None:
            return 0

        return int(rating)

    except:
        return 0

def safe_get(review, field, default=None):

    try:

        return getattr(review, field, default)

    except:
        return default

# ==========================================================
# SENTIMENT
# ==========================================================

def calculate_sentiment(avg_rating):

    if avg_rating >= 4:
        return "Positive"

    elif avg_rating >= 3:
        return "Neutral"

    return "Negative"

# ==========================================================
# DATABASE FETCH
# ==========================================================

async def get_reviews_from_db(
    company_id: int,
    limit: int = 5000
):

    async with AsyncSessionLocal() as db:

        stmt = (
            select(Review)
            .where(
                Review.company_id == company_id
            )
            .order_by(
                desc(Review.google_review_time)
            )
            .limit(limit)
        )

        result = await db.execute(stmt)

        reviews = result.scalars().all()

        logger.info(
            f"✅ DB REVIEWS FOUND => {len(reviews)}"
        )

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
        # FETCH REVIEWS
        # ==================================================

        reviews = await get_reviews_from_db(
            company_id=company_id,
            limit=5000
        )

        logger.info(
            f"✅ REVIEWS LOADED => {len(reviews)}"
        )

        # ==================================================
        # DATE FILTER
        # ==================================================

        now = datetime.utcnow()

        if days == 99999:

            start_date = datetime(2000, 1, 1)

        else:

            start_date = now - timedelta(days=days)

        filtered_reviews = []

        for review in reviews:

            try:

                created_at = (

                    safe_get(
                        review,
                        "google_review_time"
                    )

                    or

                    safe_get(
                        review,
                        "created_at"
                    )
                )

                if not created_at:
                    continue

                if isinstance(created_at, str):

                    review_date = datetime.fromisoformat(
                        created_at.replace("Z", "+00:00")
                    )

                else:

                    review_date = created_at

                if review_date.tzinfo:

                    review_date = review_date.replace(
                        tzinfo=None
                    )

                if review_date >= start_date:

                    filtered_reviews.append(review)

            except Exception as e:

                logger.warning(
                    f"Date filter failed => {e}"
                )

        reviews = filtered_reviews

        logger.info(
            f"📊 FILTERED REVIEWS => {len(reviews)}"
        )

        # ==================================================
        # KPI VARIABLES
        # ==================================================

        total_reviews = len(reviews)

        ratings = []

        positive_reviews = 0
        neutral_reviews = 0
        negative_reviews = 0

        monthly_reviews = defaultdict(int)

        monthly_positive = defaultdict(int)

        monthly_negative = defaultdict(int)

        monthly_rating_sum = defaultdict(float)

        monthly_rating_count = defaultdict(int)

        recent_reviews = 0

        # ==================================================
        # PROCESS REVIEWS
        # ==================================================

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

                created_at = (

                    safe_get(
                        review,
                        "google_review_time"
                    )

                    or

                    safe_get(
                        review,
                        "created_at"
                    )
                )

                if not created_at:
                    continue

                if isinstance(created_at, str):

                    dt = datetime.fromisoformat(
                        created_at.replace("Z", "+00:00")
                    )

                else:

                    dt = created_at

                if dt.tzinfo:

                    dt = dt.replace(
                        tzinfo=None
                    )

                month_key = dt.strftime("%Y-%m")

                monthly_reviews[month_key] += 1

                if rating >= 4:

                    monthly_positive[month_key] += 1

                elif rating <= 2:

                    monthly_negative[month_key] += 1

                monthly_rating_sum[month_key] += rating

                monthly_rating_count[month_key] += 1

                if dt >= (
                    now - timedelta(days=30)
                ):

                    recent_reviews += 1

            except Exception as e:

                logger.warning(
                    f"Monthly grouping failed => {e}"
                )

        # ==================================================
        # KPI CALCULATIONS
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

        business_health_score = round(

            (
                reputation_score * 0.5
                +
                customer_satisfaction * 0.5
            ),

            2
        )

        # ==================================================
        # EXECUTIVE RISK
        # ==================================================

        if revenue_risk >= 70:

            executive_risk = "Critical"

        elif revenue_risk >= 40:

            executive_risk = "High"

        elif revenue_risk >= 20:

            executive_risk = "Moderate"

        else:

            executive_risk = "Low"

        # ==================================================
        # RATING DISTRIBUTION
        # ==================================================

        rating_counter = Counter(ratings)

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

        monthly_positive_values = []
        monthly_negative_values = []
        monthly_average_rating = []

        for month in month_labels:

            monthly_positive_values.append(
                monthly_positive.get(month, 0)
            )

            monthly_negative_values.append(
                monthly_negative.get(month, 0)
            )

            rating_total = monthly_rating_sum.get(
                month,
                0
            )

            rating_count = monthly_rating_count.get(
                month,
                1
            )

            monthly_average_rating.append(

                round(
                    rating_total / max(1, rating_count),
                    2
                )
            )

        # ==================================================
        # FORECASTING
        # ==================================================

        predicted_next_month_reviews = 0

        if len(month_values) >= 2:

            growth = (
                month_values[-1]
                - month_values[-2]
            )

            predicted_next_month_reviews = (
                month_values[-1] + growth
            )

        elif month_values:

            predicted_next_month_reviews = int(
                month_values[-1] * 1.10
            )

        predicted_next_month_reviews = max(
            0,
            predicted_next_month_reviews
        )

        predicted_future_rating = round(

            min(
                5,
                average_rating + 0.2
            ),

            2
        )

        # ==================================================
        # EXECUTIVE SUMMARY
        # ==================================================

        executive_summary = f"""
Business reputation analysis indicates an
average customer satisfaction rating of
{average_rating}/5 across {total_reviews}
reviews.

Current reputation score is
{reputation_score}% with customer
satisfaction at {customer_satisfaction}%.

Revenue risk exposure is currently
{revenue_risk}% while overall business
health score stands at
{business_health_score}%.

AI analysis categorizes executive risk as
{executive_risk}.

Forecasting models predict future rating
stability around {predicted_future_rating}/5
with expected review growth reaching
{predicted_next_month_reviews} reviews.

Recommended executive actions:

• Improve customer complaint handling
• Increase quality monitoring
• Strengthen customer experience training
• Focus on reputation recovery campaigns
• Monitor monthly sentiment changes
• Improve response time to customer issues
"""

        # ==================================================
        # RESPONSE
        # ==================================================

        return {

            "status": "success",

            "company_id":
                company_id,

            # ==================================================
            # FRONTEND KPI COMPATIBILITY
            # ==================================================

            "total_reviews":
                total_reviews,

            "average_rating":
                average_rating,

            "avg_rating":
                average_rating,

            "negative_reviews":
                negative_reviews,

            "positive_reviews":
                positive_reviews,

            "neutral_reviews":
                neutral_reviews,

            "reputation_score":
                reputation_score,

            "customer_satisfaction":
                customer_satisfaction,

            "revenue_risk":
                revenue_risk,

            "business_health_score":
                business_health_score,

            "executive_risk":
                executive_risk,

            "predicted_rating":
                predicted_future_rating,

            "forecast_reviews":
                predicted_next_month_reviews,

            "executive_summary":
                executive_summary,

            # ==================================================
            # CHARTS
            # ==================================================

            "month_labels":
                month_labels,

            "month_values":
                month_values,

            "monthly_positive":
                monthly_positive_values,

            "monthly_negative":
                monthly_negative_values,

            "monthly_average_rating":
                monthly_average_rating,

            "rating_distribution":
                rating_distribution,

            # ==================================================
            # EXISTING STRUCTURE
            # ==================================================

            "kpis": {

                "total_reviews":
                    total_reviews,

                "average_rating":
                    average_rating,

                "reputation_score":
                    reputation_score,

                "customer_satisfaction":
                    customer_satisfaction,

                "revenue_risk":
                    revenue_risk,

                "business_health_score":
                    business_health_score,
            },

            "review_breakdown": {

                "positive_reviews":
                    positive_reviews,

                "neutral_reviews":
                    neutral_reviews,

                "negative_reviews":
                    negative_reviews,
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
                },

                "monthly_sentiment_trend": {

                    "labels":
                        month_labels,

                    "positive":
                        monthly_positive_values,

                    "negative":
                        monthly_negative_values
                },

                "monthly_rating_trend": {

                    "labels":
                        month_labels,

                    "values":
                        monthly_average_rating
                }
            },

            "insights": {

                "risk_level":
                    executive_risk,

                "executive_summary":
                    executive_summary,

                "predicted_next_month_reviews":
                    predicted_next_month_reviews,

                "predicted_future_rating":
                    predicted_future_rating,
            }
        }

    except Exception as e:

        logger.exception(
            "❌ DASHBOARD FAILED"
        )

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

# ==========================================================
# REVIEWS API
# ==========================================================

@router.get("/reviews/company/{company_id}")

async def get_company_reviews(

    request: Request,

    company_id: int,

    limit: int = Query(
        100,
        le=5000
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

                "content":
                    safe_get(
                        review,
                        "text",
                        ""
                    ),

                "created_at":

                    str(

                        safe_get(
                            review,
                            "google_review_time"
                        )

                        or

                        safe_get(
                            review,
                            "created_at",
                            "-"
                        )
                    ),

                "sentiment":
                    sentiment
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
            "❌ REVIEWS API FAILED"
        )

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )
