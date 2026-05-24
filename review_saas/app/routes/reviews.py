# ==========================================================
# FILE: app/routes/reviews.py
# TRUSTLYTICS AI — FINAL ENTERPRISE REVIEWS ENGINE
# FULLY SYNCHRONIZED WITH:
# ✅ models.py
# ✅ dashboard.py
# ✅ companies.py
# ✅ scraper.py
# ✅ PostgreSQL
# MAY 2026
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

from sqlalchemy.exc import (
    SQLAlchemyError
)

from datetime import (
    datetime,
    timedelta
)

import logging

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

    Review,

    Company
)

# ==========================================================
# SCRAPER
# ==========================================================

from app.services.scraper import (
    scrape_google_reviews
)

# ==========================================================
# LOGGER
# ==========================================================

logger = logging.getLogger(
    "app.routes.reviews"
)

# ==========================================================
# ROUTER
# ==========================================================

router = APIRouter(

    prefix="/api",

    tags=["Reviews"]
)

# ==========================================================
# SAFE HELPERS
# ==========================================================

def safe_text(value):

    try:

        if value is None:
            return ""

        return str(value).strip()

    except:

        return ""


def safe_rating(value):

    try:

        if value is None:
            return 0

        return float(value)

    except:

        return 0


# ==========================================================
# NORMALIZE REVIEW DATE
# ==========================================================

def normalize_review_date(review_date):

    try:

        if not review_date:

            return datetime.utcnow()

        lower = str(review_date).lower()

        now = datetime.utcnow()

        if "day" in lower:

            num = int(

                "".join(

                    filter(
                        str.isdigit,
                        lower
                    )
                ) or 0
            )

            return now - timedelta(days=num)

        elif "week" in lower:

            num = int(

                "".join(

                    filter(
                        str.isdigit,
                        lower
                    )
                ) or 0
            )

            return now - timedelta(days=num * 7)

        elif "month" in lower:

            num = int(

                "".join(

                    filter(
                        str.isdigit,
                        lower
                    )
                ) or 0
            )

            return now - timedelta(days=num * 30)

        elif "year" in lower:

            num = int(

                "".join(

                    filter(
                        str.isdigit,
                        lower
                    )
                ) or 0
            )

            return now - timedelta(days=num * 365)

        return now

    except:

        return datetime.utcnow()

# ==========================================================
# SAVE REVIEWS
# ==========================================================

async def save_reviews_to_database(

    company_id,
    reviews
):

    inserted = 0

    skipped = 0

    async with AsyncSessionLocal() as db:

        try:

            for review in reviews:

                try:

                    review_id = safe_text(

                        review.get(
                            "review_id"
                        )
                    )

                    if not review_id:

                        skipped += 1

                        continue

                    # ======================================
                    # DUPLICATE CHECK
                    # ======================================

                    existing_stmt = (

                        select(Review)

                        .where(

                            Review.google_review_id
                            == review_id
                        )
                    )

                    existing_result = await db.execute(
                        existing_stmt
                    )

                    existing = (
                        existing_result.scalar_one_or_none()
                    )

                    if existing:

                        skipped += 1

                        continue

                    # ======================================
                    # DATE
                    # ======================================

                    review_date = normalize_review_date(

                        review.get(
                            "review_date"
                        )
                    )

                    # ======================================
                    # SENTIMENT SCORE
                    # ======================================

                    rating = safe_rating(

                        review.get(
                            "rating"
                        )
                    )

                    if rating >= 4:

                        sentiment_score = 1.0

                    elif rating <= 2:

                        sentiment_score = -1.0

                    else:

                        sentiment_score = 0.0

                    # ======================================
                    # INSERT REVIEW
                    # ======================================

                    db_review = Review(

                        company_id=
                            company_id,

                        google_review_id=
                            review_id,

                        author_name=
                            safe_text(

                                review.get(
                                    "author_name"
                                )
                            ),

                        rating=
                            int(rating),

                        sentiment_score=
                            sentiment_score,

                        text=
                            safe_text(

                                review.get(
                                    "text"
                                )
                            ),

                        google_review_time=
                            review_date,

                        first_seen_at=
                            datetime.utcnow(),

                        review_likes=
                            int(

                                review.get(
                                    "likes",
                                    0
                                )
                            ),

                        created_at=
                            datetime.utcnow(),

                        # ==================================
                        # AI ANALYTICS PLACEHOLDERS
                        # ==================================

                        issue_category=
                            None,

                        emotion=
                            None,

                        urgency_score=
                            None,

                        ai_summary=
                            None,

                        risk_score=
                            None,

                        topic_cluster=
                            None
                    )

                    db.add(
                        db_review
                    )

                    inserted += 1

                except Exception as e:

                    logger.warning(
                        f"⚠️ REVIEW SAVE FAILED => {e}"
                    )

                    continue

            await db.commit()

            logger.info(
                f"✅ INSERTED => {inserted}"
            )

            logger.info(
                f"✅ SKIPPED => {skipped}"
            )

            return {

                "inserted":
                    inserted,

                "skipped":
                    skipped
            }

        except Exception as e:

            await db.rollback()

            logger.exception(
                "❌ DATABASE SAVE FAILED"
            )

            raise HTTPException(

                status_code=500,

                detail=str(e)
            )

# ==========================================================
# SYNC REVIEWS
# ==========================================================

@router.post(
    "/reviews/sync/{company_id}"
)

async def sync_reviews(

    request: Request,

    company_id: int,

    limit: int = Query(
        100,
        le=1000
    )
):

    try:

        logger.info(
            f"🚀 REVIEW SYNC STARTED => {company_id}"
        )

        # ==============================================
        # GET COMPANY
        # ==============================================

        async with AsyncSessionLocal() as db:

            stmt = (

                select(Company)

                .where(
                    Company.id == company_id
                )
            )

            result = await db.execute(stmt)

            company = result.scalar_one_or_none()

            if not company:

                raise HTTPException(

                    status_code=404,

                    detail="Company not found"
                )

        # ==============================================
        # SCRAPE REVIEWS
        # ==============================================

        scraped_reviews = await scrape_google_reviews(

            place_id=
                company.google_place_id,

            target_limit=
                limit
        )

        logger.info(
            f"✅ SCRAPED REVIEWS => {len(scraped_reviews)}"
        )

        # ==============================================
        # SAVE TO DATABASE
        # ==============================================

        save_result = await save_reviews_to_database(

            company_id=
                company_id,

            reviews=
                scraped_reviews
        )

        return {

            "status":
                "success",

            "company_id":
                company_id,

            "company_name":
                company.name,

            "scraped_reviews":
                len(scraped_reviews),

            "inserted_reviews":
                save_result["inserted"],

            "skipped_reviews":
                save_result["skipped"]
        }

    except HTTPException:

        raise

    except Exception as e:

        logger.exception(
            "❌ REVIEW SYNC FAILED"
        )

        raise HTTPException(

            status_code=500,

            detail=str(e)
        )

# ==========================================================
# GET COMPANY REVIEWS
# ==========================================================

@router.get(
    "/reviews/company/{company_id}"
)

async def get_company_reviews(

    request: Request,

    company_id: int,

    limit: int = Query(
        100,
        le=5000
    )
):

    try:

        async with AsyncSessionLocal() as db:

            stmt = (

                select(Review)

                .where(
                    Review.company_id == company_id
                )

                .order_by(

                    desc(
                        Review.google_review_time
                    )
                )

                .limit(limit)
            )

            result = await db.execute(
                stmt
            )

            reviews = result.scalars().all()

            logger.info(
                f"✅ REVIEWS FETCHED => {len(reviews)}"
            )

            formatted = []

            for review in reviews:

                rating = safe_rating(
                    review.rating
                )

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

                    "id":
                        review.id,

                    "review_id":
                        review.google_review_id,

                    "author_name":
                        safe_text(
                            review.author_name
                        ),

                    "rating":
                        rating,

                    "text":
                        safe_text(
                            review.text
                        ),

                    "review_likes":
                        review.review_likes,

                    "google_review_time":

                        str(
                            review.google_review_time
                        )

                        if review.google_review_time
                        else None,

                    "created_at":

                        str(
                            review.created_at
                        )

                        if review.created_at
                        else None,

                    "sentiment":
                        sentiment,

                    "issue_category":
                        review.issue_category,

                    "emotion":
                        review.emotion,

                    "urgency_score":
                        review.urgency_score,

                    "risk_score":
                        review.risk_score
                })

            return {

                "status":
                    "success",

                "company_id":
                    company_id,

                "total_reviews":
                    len(formatted),

                "reviews":
                    formatted
            }

    except SQLAlchemyError as e:

        logger.exception(
            "❌ DATABASE QUERY FAILED"
        )

        raise HTTPException(

            status_code=500,

            detail=str(e)
        )

    except Exception as e:

        logger.exception(
            "❌ REVIEWS API FAILED"
        )

        raise HTTPException(

            status_code=500,

            detail=str(e)
        )

# ==========================================================
# DELETE REVIEW
# ==========================================================

@router.delete(
    "/reviews/{review_id}"
)

async def delete_review(

    request: Request,

    review_id: int
):

    try:

        async with AsyncSessionLocal() as db:

            stmt = (

                select(Review)

                .where(
                    Review.id == review_id
                )
            )

            result = await db.execute(
                stmt
            )

            review = result.scalar_one_or_none()

            if not review:

                raise HTTPException(

                    status_code=404,

                    detail="Review not found"
                )

            await db.delete(review)

            await db.commit()

            logger.info(
                f"🗑️ REVIEW DELETED => {review_id}"
            )

            return {

                "status":
                    "success",

                "message":
                    "Review deleted successfully"
            }

    except Exception as e:

        logger.exception(
            "❌ DELETE REVIEW FAILED"
        )

        raise HTTPException(

            status_code=500,

            detail=str(e)
        )

# ==========================================================
# HEALTH CHECK
# ==========================================================

@router.get(
    "/reviews/health"
)

async def reviews_health():

    return {

        "status":
            "healthy",

        "service":
            "reviews",

        "timestamp":
            str(
                datetime.utcnow()
            )
    }
