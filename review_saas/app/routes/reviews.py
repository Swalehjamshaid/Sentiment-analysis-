# ==========================================================
# FILE: app/routes/reviews.py
# TRUSTLYTICS AI — ENTERPRISE REVIEW ROUTER
# FULLY ALIGNED WITH MAIN.PY + SCRAPER.PY
# MAY 2026
# ==========================================================

from __future__ import annotations

import traceback

from typing import Any

from fastapi import (
    APIRouter,
    HTTPException,
    Depends,
    Request
)

from fastapi.responses import JSONResponse

from loguru import logger

# ==========================================================
# DATABASE
# ==========================================================

from app.core.db import get_db

from sqlalchemy.ext.asyncio import AsyncSession

# ==========================================================
# MODELS
# ==========================================================

from app.models.models import (
    Company,
    Review
)

# ==========================================================
# SQLALCHEMY
# ==========================================================

from sqlalchemy import (
    select,
    func,
    delete
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

        "message": "Reviews router working successfully"
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

            select(Company).where(
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

        total_reviews = len(reviews)

        logger.info(
            f"📊 TOTAL REVIEWS => {total_reviews}"
        )

        reviews_data = []

        for review in reviews:

            reviews_data.append({

                "id": review.id,

                "reviewer_name":
                    getattr(
                        review,
                        "reviewer_name",
                        "Anonymous"
                    ),

                "rating":
                    getattr(
                        review,
                        "rating",
                        0
                    ),

                "review_text":
                    getattr(
                        review,
                        "review_text",
                        ""
                    ),

                "review_date":
                    str(
                        getattr(
                            review,
                            "review_date",
                            ""
                        )
                    ),

                "sentiment":
                    getattr(
                        review,
                        "sentiment",
                        "neutral"
                    ),

                "source":
                    getattr(
                        review,
                        "source",
                        "Google"
                    )
            })

        return {

            "success": True,

            "company_id": company_id,

            "company_name":
                company.name,

            "total_reviews":
                total_reviews,

            "reviews":
                reviews_data
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

        # ==================================================
        # COMPANY VALIDATION
        # ==================================================

        company_query = await db.execute(

            select(Company).where(
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
        # SCRAPER EXECUTION
        # ==================================================

        scraper_result = await sync_company_reviews(

            db=db,

            company=company
        )

        logger.success(
            f"✅ SCRAPER COMPLETED => {company.name}"
        )

        # ==================================================
        # REVIEW COUNT
        # ==================================================

        review_count_query = await db.execute(

            select(func.count())

            .select_from(Review)

            .where(
                Review.company_id == company_id
            )
        )

        total_reviews = review_count_query.scalar()

        logger.info(
            f"📊 TOTAL REVIEWS => {total_reviews}"
        )

        return {

            "success": True,

            "message":
                "Reviews synced successfully",

            "company_id":
                company_id,

            "company_name":
                company.name,

            "total_reviews":
                total_reviews,

            "scraper_result":
                scraper_result
        }

    except HTTPException:

        raise

    except Exception as e:

        logger.error(
            f"❌ REVIEW SYNC FAILED => {e}"
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

            delete(Review).where(
                Review.company_id == company_id
            )
        )

        await db.commit()

        logger.success(
            "✅ REVIEWS DELETED"
        )

        return {

            "success": True,

            "message":
                "Reviews deleted successfully"
        }

    except Exception as e:

        logger.error(
            f"❌ DELETE FAILED => {e}"
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

        total_reviews = total_query.scalar()

        avg_query = await db.execute(

            select(func.avg(Review.rating))

            .where(
                Review.company_id == company_id
            )
        )

        average_rating = avg_query.scalar()

        return {

            "success": True,

            "company_id":
                company_id,

            "total_reviews":
                total_reviews or 0,

            "average_rating":
                round(float(average_rating or 0), 2)
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
