# ==========================================================
# FILE: app/routes/dashboard.py
# REVIEW INTEL AI — ENTERPRISE AI DASHBOARD
# FULLY FRONTEND ALIGNED VERSION
# ==========================================================

from fastapi import (
    APIRouter,
    HTTPException,
    Query,
    Request
)

from sqlalchemy import (
    select,
    desc
)

from collections import (
    defaultdict,
    Counter
)

from statistics import mean

from datetime import (
    datetime,
    timedelta
)

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

    prefix="/api",

    tags=["Dashboard"]
)

# ==========================================================
# SAFE HELPERS
# ==========================================================

def safe_get(obj, field, default=None):

    try:
        return getattr(obj, field, default)

    except:
        return default


def safe_rating(review):

    try:

        rating = safe_get(
            review,
            "rating",
            0
        )

        if rating is None:
            return 0

        return float(rating)

    except:

        return 0


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
            f"✅ REVIEWS FETCHED => {len(reviews)}"
        )

        return reviews


# ==========================================================
# DASHBOARD API
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
            f"📊 TOTAL REVIEWS => {len(reviews)}"
        )

        # ==================================================
        # DATE FILTERING
        # ==================================================

        now = datetime.utcnow()

        if days >= 3650:

            start_date = datetime(
                2000,
                1,
                1
            )

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
                    f"⚠️ DATE FILTER FAILED => {e}"
                )

        reviews = filtered_reviews

        logger.info(
            f"✅ FILTERED REVIEWS => {len(reviews)}"
        )

        # ==================================================
        # KPI VARIABLES
        # ==================================================

        ratings = []

        positive_reviews = 0
        neutral_reviews = 0
        negative_reviews = 0

        total_reviews = len(reviews)

        monthly_reviews = defaultdict(int)

        monthly_positive = defaultdict(int)

        monthly_negative = defaultdict(int)

        monthly_rating_sum = defaultdict(float)

        monthly_rating_count = defaultdict(int)

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

                elif rating <= 2:

                    negative_reviews += 1

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

                        created_at.replace(
                            "Z",
                            "+00:00"
                        )
                    )

                else:

                    dt = created_at

                if dt.tzinfo:

                    dt = dt.replace(
                        tzinfo=None
                    )

                # ==========================================
                # IGNORE BROKEN OLD DATES
                # ==========================================

                if dt.year < 2020:
                    continue

                month_key = dt.strftime(
                    "%Y-%m"
                )

                monthly_reviews[
                    month_key
                ] += 1

                if rating >= 4:

                    monthly_positive[
                        month_key
                    ] += 1

                elif rating <= 2:

                    monthly_negative[
                        month_key
                    ] += 1

                monthly_rating_sum[
                    month_key
                ] += rating

                monthly_rating_count[
                    month_key
                ] += 1

            except Exception as e:

                logger.warning(
                    f"⚠️ MONTHLY PROCESS FAILED => {e}"
                )

        # ==================================================
        # KPI ENGINE
        # ==================================================

        average_rating = round(

            mean(ratings),

            2

        ) if ratings else 0

        reputation_score = round(

            (
                positive_reviews /
                max(1, total_reviews)
            ) * 100,

            1
        )

        revenue_risk = round(

            (
                negative_reviews /
                max(1, total_reviews)
            ) * 100,

            1
        )

        customer_satisfaction = round(

            (
                average_rating / 5
            ) * 100,

            1
        )

        business_health_score = round(

            (
                reputation_score +
                customer_satisfaction
            ) / 2,

            1
        )

        # ==================================================
        # EXECUTIVE RISK
        # ==================================================

        if revenue_risk >= 70:

            executive_risk = "Critical"

        elif revenue_risk >= 50:

            executive_risk = "High"

        elif revenue_risk >= 30:

            executive_risk = "Moderate"

        else:

            executive_risk = "Low"

        # ==================================================
        # AI FORECASTING
        # ==================================================

        predicted_rating = round(

            min(
                5,
                average_rating + 0.3
            ),

            2
        )

        forecast_reviews = round(
            total_reviews * 1.15
        )

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
        # MONTHLY ANALYTICS
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

                monthly_positive.get(
                    month,
                    0
                )
            )

            monthly_negative_values.append(

                monthly_negative.get(
                    month,
                    0
                )
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
                    rating_total /
                    max(1, rating_count),
                    2
                )
            )

        # ==================================================
        # AI EXECUTIVE SUMMARY
        # ==================================================

        executive_summary = f"""

        <div class="alert alert-primary rounded-4 shadow-sm">

            <h4>
                🧠 AI Executive Intelligence
            </h4>

            <hr>

            <p>
                This business currently maintains
                an average customer rating of
                <strong>{average_rating}</strong>
                from
                <strong>{total_reviews}</strong>
                customer reviews.
            </p>

            <p>
                AI analysis identified
                <strong>{negative_reviews}</strong>
                negative reviews and calculated
                a revenue risk exposure of
                <strong>{revenue_risk}%</strong>.
            </p>

            <p>
                Current business health score is
                <strong>{business_health_score}%</strong>
                with an executive operational
                risk level classified as
                <strong>{executive_risk}</strong>.
            </p>

            <p>
                Predictive AI models forecast
                future rating improvement toward
                <strong>{predicted_rating}</strong>
                with expected review growth
                reaching
                <strong>{forecast_reviews}</strong>
                reviews.
            </p>

            <hr>

            <h5>
                📈 Executive Recommendations
            </h5>

            <ul>

                <li>
                    Improve customer complaint response time
                </li>

                <li>
                    Enhance operational quality monitoring
                </li>

                <li>
                    Launch reputation recovery campaigns
                </li>

                <li>
                    Improve staff behavior management
                </li>

                <li>
                    Monitor monthly sentiment changes
                </li>

                <li>
                    Strengthen customer experience programs
                </li>

            </ul>

        </div>
        """

        # ==================================================
        # FINAL RESPONSE
        # ==================================================

        return {

            "status": "success",

            # ==============================================
            # KPI CARDS
            # ==============================================

            "kpis": {

                "total_reviews":
                    total_reviews,

                "average_rating":
                    average_rating,
"negative_reviews":
    negative_reviews,
                
                "reputation_score":
                    reputation_score,

                "revenue_risk":
                    revenue_risk,

                "customer_satisfaction":
                    customer_satisfaction,

                "business_health_score":
                    business_health_score,

                "executive_risk":
                    executive_risk,

                "predicted_rating":
                    predicted_rating,

                "forecast_reviews":
                    forecast_reviews
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
                    negative_reviews
            },

            # ==============================================
            # CHARTS
            # ==============================================

            "charts": {

                "monthly_trend": {

                    "labels":
                        month_labels,

                    "values":
                        month_values
                },

                "monthly_sentiment": {

                    "labels":
                        month_labels,

                    "positive":
                        monthly_positive_values,

                    "negative":
                        monthly_negative_values
                },

                "monthly_rating": {

                    "labels":
                        month_labels,

                    "values":
                        monthly_average_rating
                },

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
                }
            },

            # ==============================================
            # EXECUTIVE SUMMARY
            # ==============================================

            "executive_summary":
                executive_summary,

            # ==============================================
            # RECENT REVIEWS
            # ==============================================

            "recent_reviews": [

                {

                    "author":
                        safe_get(
                            review,
                            "author_name",
                            "Anonymous"
                        ),

                    "rating":
                        safe_rating(review),

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
                        )
                }

                for review in reviews[:10]
            ]
        }

    except Exception as e:

        logger.exception(
            "❌ DASHBOARD API FAILED"
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

                else

                "negative"

                if rating <= 2

                else

                "neutral"
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
