# ==========================================================
# FILE: app/routes/reviews.py
# TRUSTLYTICS AI SAAS - ENTERPRISE REVIEWS ROUTES
# ==========================================================

import logging
import traceback

from typing import (
    List,
    Dict,
    Any
)

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status
)

from sqlalchemy import (
    select,
    func,
    desc
)

from sqlalchemy.ext.asyncio import AsyncSession

# ==========================================================
# DATABASE IMPORT
# ==========================================================

# IMPORTANT:
# Change this import ONLY if your get_db()
# exists somewhere else.

from app.db.database import get_db

# ==========================================================
# MODELS
# ==========================================================

from app.core.models import Review

# ==========================================================
# SCRAPER
# ==========================================================

from app.services.scraper import (
    fetch_reviews_from_google
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
    prefix="/reviews",
    tags=["Reviews"]
)

# ==========================================================
# HEALTH CHECK
# ==========================================================

@router.get("/health")

async def reviews_health():

    return {

        "success": True,

        "service":
            "reviews",

        "status":
            "healthy"
    }

# ==========================================================
# SYNC REVIEWS
# ==========================================================

@router.post("/sync")

async def sync_reviews(

    place_id: str,

    company_id: int,

    target_limit: int = 100,

    db: AsyncSession = Depends(get_db)
):

    logger.info(
        f"🚀 Review sync started | company={company_id}"
    )

    try:

        reviews = await fetch_reviews_from_google(

            place_id=
                place_id,

            company_id=
                company_id,

            session=
                db,

            target_limit=
                target_limit
        )

        logger.info(
            f"✅ Sync completed | inserted={len(reviews)}"
        )

        return {

            "success":
                True,

            "company_id":
                company_id,

            "inserted_reviews":
                len(reviews),

            "reviews":
                reviews
        }

    except Exception as e:

        logger.exception(
            f"❌ Sync failed: {e}"
        )

        raise HTTPException(

            status_code=
                status.HTTP_500_INTERNAL_SERVER_ERROR,

            detail=
                str(e)
        )

# ==========================================================
# GET ALL REVIEWS
# ==========================================================

@router.get("/all")

async def get_all_reviews(

    company_id: int,

    limit: int = Query(
        default=50,
        le=500
    ),

    db: AsyncSession = Depends(get_db)
):

    try:

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

        response = []

        for review in reviews:

            response.append({

                "id":
                    review.id,

                "company_id":
                    review.company_id,

                "google_review_id":
                    review.google_review_id,

                "author_name":
                    review.author_name,

                "rating":
                    review.rating,

                "text":
                    review.text,

                "sentiment_score":
                    review.sentiment_score,

                "review_likes":
                    review.review_likes,

                "google_review_time":
                    review.google_review_time,

                "first_seen_at":
                    review.first_seen_at,

                "created_at":
                    review.created_at
            })

        return {

            "success":
                True,

            "count":
                len(response),

            "reviews":
                response
        }

    except Exception as e:

        logger.exception(
            f"❌ Get reviews failed: {e}"
        )

        raise HTTPException(

            status_code=
                status.HTTP_500_INTERNAL_SERVER_ERROR,

            detail=
                str(e)
        )

# ==========================================================
# GET SINGLE REVIEW
# ==========================================================

@router.get("/{review_id}")

async def get_review(

    review_id: int,

    db: AsyncSession = Depends(get_db)
):

    try:

        stmt = select(Review).where(
            Review.id == review_id
        )

        result = await db.execute(
            stmt
        )

        review = result.scalar_one_or_none()

        if not review:

            raise HTTPException(

                status_code=
                    status.HTTP_404_NOT_FOUND,

                detail=
                    "Review not found"
            )

        return {

            "success":
                True,

            "review": {

                "id":
                    review.id,

                "company_id":
                    review.company_id,

                "google_review_id":
                    review.google_review_id,

                "author_name":
                    review.author_name,

                "rating":
                    review.rating,

                "text":
                    review.text,

                "sentiment_score":
                    review.sentiment_score,

                "review_likes":
                    review.review_likes,

                "google_review_time":
                    review.google_review_time,

                "first_seen_at":
                    review.first_seen_at,

                "created_at":
                    review.created_at
            }
        }

    except HTTPException:
        raise

    except Exception as e:

        logger.exception(
            f"❌ Get review failed: {e}"
        )

        raise HTTPException(

            status_code=
                status.HTTP_500_INTERNAL_SERVER_ERROR,

            detail=
                str(e)
        )

# ==========================================================
# DASHBOARD ANALYTICS
# ==========================================================

@router.get("/dashboard/stats")

async def dashboard_stats(

    company_id: int,

    db: AsyncSession = Depends(get_db)
):

    try:

        # ==================================================
        # TOTAL REVIEWS
        # ==================================================

        total_stmt = (

            select(
                func.count(Review.id)
            )

            .where(
                Review.company_id == company_id
            )
        )

        total_result = await db.execute(
            total_stmt
        )

        total_reviews = (
            total_result.scalar() or 0
        )

        # ==================================================
        # AVERAGE RATING
        # ==================================================

        avg_stmt = (

            select(
                func.avg(Review.rating)
            )

            .where(
                Review.company_id == company_id
            )
        )

        avg_result = await db.execute(
            avg_stmt
        )

        average_rating = avg_result.scalar()

        if average_rating is None:
            average_rating = 0

        average_rating = round(
            float(average_rating),
            2
        )

        # ==================================================
        # POSITIVE REVIEWS
        # ==================================================

        positive_stmt = (

            select(
                func.count(Review.id)
            )

            .where(
                Review.company_id == company_id
            )

            .where(
                Review.rating >= 4
            )
        )

        positive_result = await db.execute(
            positive_stmt
        )

        positive_reviews = (
            positive_result.scalar() or 0
        )

        # ==================================================
        # NEGATIVE REVIEWS
        # ==================================================

        negative_stmt = (

            select(
                func.count(Review.id)
            )

            .where(
                Review.company_id == company_id
            )

            .where(
                Review.rating <= 2
            )
        )

        negative_result = await db.execute(
            negative_stmt
        )

        negative_reviews = (
            negative_result.scalar() or 0
        )

        # ==================================================
        # RATING DISTRIBUTION
        # ==================================================

        rating_distribution = {}

        for rating in range(1, 6):

            stmt = (

                select(
                    func.count(Review.id)
                )

                .where(
                    Review.company_id == company_id
                )

                .where(
                    Review.rating == rating
                )
            )

            result = await db.execute(
                stmt
            )

            rating_distribution[str(rating)] = (
                result.scalar() or 0
            )

        # ==================================================
        # RECENT REVIEWS
        # ==================================================

        recent_stmt = (

            select(Review)

            .where(
                Review.company_id == company_id
            )

            .order_by(
                desc(Review.created_at)
            )

            .limit(10)
        )

        recent_result = await db.execute(
            recent_stmt
        )

        recent_reviews = (
            recent_result.scalars().all()
        )

        recent_reviews_data = []

        for review in recent_reviews:

            recent_reviews_data.append({

                "author_name":
                    review.author_name,

                "rating":
                    review.rating,

                "text":
                    review.text,

                "review_likes":
                    review.review_likes,

                "created_at":
                    review.created_at
            })

        # ==================================================
        # RESPONSE
        # ==================================================

        return {

            "success":
                True,

            "dashboard": {

                "total_reviews":
                    total_reviews,

                "average_rating":
                    average_rating,

                "positive_reviews":
                    positive_reviews,

                "negative_reviews":
                    negative_reviews,

                "rating_distribution":
                    rating_distribution,

                "recent_reviews":
                    recent_reviews_data
            }
        }

    except Exception as e:

        logger.exception(
            f"❌ Dashboard stats failed: {e}"
        )

        raise HTTPException(

            status_code=
                status.HTTP_500_INTERNAL_SERVER_ERROR,

            detail=
                str(e)
        )

# ==========================================================
# DELETE REVIEW
# ==========================================================

@router.delete("/{review_id}")

async def delete_review(

    review_id: int,

    db: AsyncSession = Depends(get_db)
):

    try:

        stmt = select(Review).where(
            Review.id == review_id
        )

        result = await db.execute(
            stmt
        )

        review = result.scalar_one_or_none()

        if not review:

            raise HTTPException(

                status_code=
                    status.HTTP_404_NOT_FOUND,

                detail=
                    "Review not found"
            )

        await db.delete(
            review
        )

        await db.commit()

        logger.info(
            f"🗑️ Review deleted | id={review_id}"
        )

        return {

            "success":
                True,

            "message":
                "Review deleted successfully"
        }

    except HTTPException:
        raise

    except Exception as e:

        await db.rollback()

        logger.exception(
            f"❌ Delete failed: {e}"
        )

        raise HTTPException(

            status_code=
                status.HTTP_500_INTERNAL_SERVER_ERROR,

            detail=
                str(e)
        )
