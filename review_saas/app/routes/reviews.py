# ==========================================================
# FILE: app/routes/reviews.py
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

from app.models.models import (
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

async def test_route():

    return {

        "success": True,

        "message": "Reviews route working"
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

        query = await db.execute(

            select(Review)

            .where(
                Review.company_id == company_id
            )
        )

        reviews = query.scalars().all()

        return {

            "success": True,

            "total_reviews": len(reviews),

            "reviews": [

                {

                    "id": r.id,

                    "reviewer_name":
                        getattr(
                            r,
                            "reviewer_name",
                            "Anonymous"
                        ),

                    "rating":
                        getattr(
                            r,
                            "rating",
                            0
                        ),

                    "review_text":
                        getattr(
                            r,
                            "review_text",
                            ""
                        ),

                    "source":
                        getattr(
                            r,
                            "source",
                            "Google"
                        )
                }

                for r in reviews
            ]
        }

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

        result = await sync_company_reviews(

            db=db,

            company=company
        )

        review_count_query = await db.execute(

            select(func.count())

            .select_from(Review)

            .where(
                Review.company_id == company_id
            )
        )

        total_reviews = review_count_query.scalar()

        logger.success(
            f"✅ REVIEW SYNC COMPLETED => {total_reviews}"
        )

        return {

            "success": True,

            "company_id": company_id,

            "company_name": company.name,

            "total_reviews": total_reviews,

            "scraper_result": result
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

        await db.execute(

            delete(Review)

            .where(
                Review.company_id == company_id
            )
        )

        await db.commit()

        return {

            "success": True,

            "message": "Reviews deleted successfully"
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
