# ==========================================================
# FILE: app/routes/reviews.py
# FULLY ALIGNED WITH YOUR REAL MODELS
# ==========================================================

from __future__ import annotations

import traceback

from fastapi import (
    APIRouter,
    Depends,
    HTTPException
)

from fastapi.responses import JSONResponse

from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import (
    select,
    delete,
    func
)

from loguru import logger

# ==========================================================
# DATABASE
# ==========================================================

from app.core.db import get_db

# ==========================================================
# MODELS
# ==========================================================

from app.core.models import (
    Company,
    Review
)

# ==========================================================
# SCRAPER
# ==========================================================

from app.services.scraper import (
    sync_company_reviews
)

# ==========================================================
# ROUTER
# ==========================================================

router = APIRouter(
    prefix="/api/reviews",
    tags=["Reviews"]
)

# ==========================================================
# TEST ROUTE
# ==========================================================

@router.get("/test")
async def test_reviews():

    return {
        "success": True,
        "message": "Reviews router working"
    }

# ==========================================================
# GET COMPANY REVIEWS
# ==========================================================

@router.get("/company/{company_id}")

async def get_company_reviews(

    company_id: int,

    db: AsyncSession = Depends(get_db)
):

    try:

        logger.info(
            f"📥 FETCHING REVIEWS => {company_id}"
        )

        company_query = await db.execute(

            select(Company)

            .where(
                Company.id == company_id
            )
        )

        company = company_query.scalar_one_or_none()

        if not company:

            raise HTTPException(

                status_code=404,

                detail="Company not found"
            )

        reviews_query = await db.execute(

            select(Review)

            .where(
                Review.company_id == company_id
            )

            .order_by(
                Review.created_at.desc()
            )
        )

        reviews = reviews_query.scalars().all()

        logger.success(
            f"✅ REVIEWS FOUND => {len(reviews)}"
        )

        formatted_reviews = []

        for review in reviews:

            formatted_reviews.append({

                "id":
                    review.id,

                # FRONTEND EXPECTS author
                "author":
                    review.author_name,

                # FRONTEND EXPECTS content
                "content":
                    review.text,

                "rating":
                    review.rating,

                "created_at":
                    str(review.created_at),

                "google_review_time":
                    str(review.google_review_time),

                "sentiment_score":
                    review.sentiment_score,

                "review_likes":
                    review.review_likes,

                "issue_category":
                    review.issue_category,

                "emotion":
                    review.emotion,

                "urgency_score":
                    review.urgency_score,

                "risk_score":
                    review.risk_score,

                "ai_summary":
                    review.ai_summary
            })

        return {

            "success": True,

            "company_id":
                company.id,

            "company_name":
                company.name,

            "total_reviews":
                len(formatted_reviews),

            "reviews":
                formatted_reviews
        }

    except HTTPException:

        raise

    except Exception as e:

        logger.error(
            f"❌ GET REVIEWS ERROR => {e}"
        )

        logger.error(
            traceback.format_exc()
        )

        return JSONResponse(

            status_code=500,

            content={

                "success": False,

                "message": str(e)
            }
        )

# ==========================================================
# SYNC REVIEWS
# ==========================================================

@router.post("/sync/{company_id}")

async def sync_reviews(

    company_id: int,

    db: AsyncSession = Depends(get_db)
):

    try:

        logger.info(
            f"🚀 REVIEW SYNC STARTED => {company_id}"
        )

        company_query = await db.execute(

            select(Company)

            .where(
                Company.id == company_id
            )
        )

        company = company_query.scalar_one_or_none()

        if not company:

            raise HTTPException(

                status_code=404,

                detail="Company not found"
            )

        logger.success(
            f"✅ COMPANY FOUND => {company.name}"
        )

        # ==================================================
        # RUN SCRAPER
        # ==================================================

        scraper_result = await sync_company_reviews(

            db=db,

            company=company
        )

        logger.success(
            "✅ SCRAPER COMPLETED"
        )

        # ==================================================
        # TOTAL REVIEWS
        # ==================================================

        total_query = await db.execute(

            select(func.count())

            .select_from(Review)

            .where(
                Review.company_id == company_id
            )
        )

        total_reviews = total_query.scalar() or 0

        logger.success(
            f"✅ TOTAL REVIEWS => {total_reviews}"
        )

        return {

            "success": True,

            "message":
                "Reviews synced successfully",

            "reviews_collected":
                scraper_result.get(
                    "reviews_collected",
                    0
                ),

            "total_reviews":
                total_reviews,

            "company_id":
                company_id
        }

    except HTTPException:

        raise

    except Exception as e:

        logger.error(
            f"❌ SYNC ERROR => {e}"
        )

        logger.error(
            traceback.format_exc()
        )

        return JSONResponse(

            status_code=500,

            content={

                "success": False,

                "message": str(e)
            }
        )

# ==========================================================
# DELETE REVIEWS
# ==========================================================

@router.delete("/delete/{company_id}")

async def delete_reviews(

    company_id: int,

    db: AsyncSession = Depends(get_db)
):

    try:

        logger.warning(
            f"🗑️ DELETING REVIEWS => {company_id}"
        )

        await db.execute(

            delete(Review)

            .where(
                Review.company_id == company_id
            )
        )

        await db.commit()

        return {

            "success": True,

            "message":
                "Reviews deleted successfully"
        }

    except Exception as e:

        logger.error(
            f"❌ DELETE ERROR => {e}"
        )

        logger.error(
            traceback.format_exc()
        )

        return JSONResponse(

            status_code=500,

            content={

                "success": False,

                "message": str(e)
            }
        )

# ==========================================================
# REVIEW STATS
# ==========================================================

@router.get("/stats/{company_id}")

async def review_stats(

    company_id: int,

    db: AsyncSession = Depends(get_db)
):

    try:

        total_query = await db.execute(

            select(func.count())

            .select_from(Review)

            .where(
                Review.company_id == company_id
            )
        )

        total_reviews = total_query.scalar() or 0

        avg_query = await db.execute(

            select(func.avg(Review.rating))

            .where(
                Review.company_id == company_id
            )
        )

        average_rating = avg_query.scalar() or 0

        return {

            "success": True,

            "total_reviews":
                total_reviews,

            "average_rating":
                round(float(average_rating), 2)
        }

    except Exception as e:

        logger.error(
            f"❌ STATS ERROR => {e}"
        )

        logger.error(
            traceback.format_exc()
        )

        return JSONResponse(

            status_code=500,

            content={

                "success": False,

                "message": str(e)
            }
        )
