# ==========================================================
# FILE: app/routes/reviews.py
# TRUSTLYTICS AI SAAS - FINAL ENTERPRISE REVIEWS ROUTER
# FIXES:
# ✅ /api/reviews/all
# ✅ PostgreSQL review insertion
# ✅ Dashboard review loading
# ✅ Sync Reviews button
# ✅ Duplicate review protection
# ✅ Railway route registration
# ==========================================================

import logging
import traceback

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

from sqlalchemy.ext.asyncio import (
    AsyncSession
)

# ==========================================================
# DATABASE
# ==========================================================

from app.core.db import (
    get_db
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

        "service": "reviews",

        "status": "healthy"
    }

# ==========================================================
# SAVE REVIEWS TO POSTGRESQL
# ==========================================================

async def save_reviews(

    db: AsyncSession,

    company_id: int,

    scraped_reviews: list
):

    inserted_reviews = []

    for item in scraped_reviews:

        try:

            review_id = item.get(
                "review_id"
            )

            # ==============================================
            # DUPLICATE CHECK
            # ==============================================

            stmt = select(
                Review
            ).where(
                Review.google_review_id ==
                review_id
            )

            result = await db.execute(
                stmt
            )

            existing_review = (
                result.scalar_one_or_none()
            )

            if existing_review:
                continue

            # ==============================================
            # CREATE REVIEW OBJECT
            # ==============================================

            review = Review(

                company_id=company_id,

                google_review_id=review_id,

                author_name=item.get(
                    "author_name",
                    "Anonymous"
                ),

                rating=item.get(
                    "rating",
                    5
                ),

                text=item.get(
                    "text",
                    ""
                ),

                review_likes=item.get(
                    "likes",
                    0
                )
            )

            db.add(review)

            inserted_reviews.append({

                "author_name":
                    review.author_name,

                "rating":
                    review.rating,

                "text":
                    review.text[:100]
            })

        except Exception as inner_error:

            logger.error(
                f"❌ REVIEW INSERT FAILED: {inner_error}"
            )

    await db.commit()

    return inserted_reviews

# ==========================================================
# SYNC REVIEWS
# ==========================================================

@router.post("/sync")

async def sync_reviews(

    company_id: int,

    place_id: str,

    target_limit: int = 100,

    db: AsyncSession = Depends(get_db)
):

    logger.info(
        f"🚀 SYNC STARTED => company={company_id}"
    )

    try:

        # ==============================================
        # COMPANY VALIDATION
        # ==============================================

        stmt = select(
            Company
        ).where(
            Company.id == company_id
        )

        result = await db.execute(
            stmt
        )

        company = result.scalar_one_or_none()

        if not company:

            raise HTTPException(

                status_code=
                    status.HTTP_404_NOT_FOUND,

                detail=
                    "Company not found"
            )

        # ==============================================
        # SCRAPE REVIEWS
        # ==============================================

        scraped_reviews = await scrape_google_reviews(

            place_id=place_id,

            target_limit=target_limit
        )

        logger.info(
            f"✅ SCRAPED => {len(scraped_reviews)}"
        )

        # ==============================================
        # SAVE REVIEWS
        # ==============================================

        inserted_reviews = await save_reviews(

            db=db,

            company_id=company_id,

            scraped_reviews=scraped_reviews
        )

        logger.info(
            f"✅ INSERTED => {len(inserted_reviews)}"
        )

        return {

            "success": True,

            "company_id": company_id,

            "scraped_reviews":
                len(scraped_reviews),

            "inserted_reviews":
                len(inserted_reviews),

            "reviews":
                inserted_reviews
        }

    except HTTPException:
        raise

    except Exception as e:

        logger.exception(
            f"❌ SYNC FAILED => {e}"
        )

        logger.error(
            traceback.format_exc()
        )

        raise HTTPException(

            status_code=
                status.HTTP_500_INTERNAL_SERVER_ERROR,

            detail=
                str(e)
        )

# ==========================================================
# FRONTEND INGEST ROUTE
# ==========================================================

@router.post("/ingest/{company_id}")

async def ingest_reviews(

    company_id: int,

    db: AsyncSession = Depends(get_db)
):

    logger.info(
        f"🚀 INGEST STARTED => company={company_id}"
    )

    try:

        stmt = select(
            Company
        ).where(
            Company.id == company_id
        )

        result = await db.execute(
            stmt
        )

        company = result.scalar_one_or_none()

        if not company:

            raise HTTPException(

                status_code=
                    status.HTTP_404_NOT_FOUND,

                detail=
                    "Company not found"
            )

        # ==============================================
        # PLACE ID
        # ==============================================

        place_id = getattr(

            company,

            "google_place_id",

            None
        )

        if not place_id:

            raise HTTPException(

                status_code=
                    status.HTTP_400_BAD_REQUEST,

                detail=
                    "Company missing Google Place ID"
            )

        # ==============================================
        # SCRAPE
        # ==============================================

        scraped_reviews = await scrape_google_reviews(

            place_id=place_id,

            target_limit=100
        )

        logger.info(
            f"✅ SCRAPED => {len(scraped_reviews)}"
        )

        # ==============================================
        # SAVE
        # ==============================================

        inserted_reviews = await save_reviews(

            db=db,

            company_id=company_id,

            scraped_reviews=scraped_reviews
        )

        logger.info(
            f"✅ INSERTED => {len(inserted_reviews)}"
        )

        return {

            "success": True,

            "company_id":
                company_id,

            "reviews_collected":
                len(inserted_reviews),

            "reviews":
                inserted_reviews
        }

    except HTTPException:
        raise

    except Exception as e:

        logger.exception(
            f"❌ INGEST FAILED => {e}"
        )

        logger.error(
            traceback.format_exc()
        )

        raise HTTPException(

            status_code=
                status.HTTP_500_INTERNAL_SERVER_ERROR,

            detail=
                str(e)
        )

# ==========================================================
# GET ALL REVIEWS
# THIS FIXES:
# /api/reviews/all?company_id=1
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

                "author_name":
                    review.author_name,

                "rating":
                    review.rating,

                "text":
                    review.text,

                "likes":
                    review.review_likes,

                "created_at":
                    review.created_at
            })

        return {

            "success": True,

            "count":
                len(response),

            "reviews":
                response
        }

    except Exception as e:

        logger.exception(
            f"❌ GET REVIEWS FAILED => {e}"
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

        # ==============================================
        # TOTAL REVIEWS
        # ==============================================

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

        # ==============================================
        # AVG RATING
        # ==============================================

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

        # ==============================================
        # RECENT REVIEWS
        # ==============================================

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

                "created_at":
                    review.created_at
            })

        return {

            "success": True,

            "dashboard": {

                "total_reviews":
                    total_reviews,

                "average_rating":
                    average_rating,

                "recent_reviews":
                    recent_reviews_data
            }
        }

    except Exception as e:

        logger.exception(
            f"❌ DASHBOARD STATS FAILED => {e}"
        )

        raise HTTPException(

            status_code=
                status.HTTP_500_INTERNAL_SERVER_ERROR,

            detail=
                str(e)
        )
