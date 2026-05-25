# ==========================================================
# FILE: app/routes/reviews.py
# ==========================================================

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from loguru import logger
from datetime import datetime

from app.db import get_db
from app.models import Company, Review

# IMPORTANT:
# This import MUST match your scraper.py filename and function
from app.scraper import scrape_google_reviews


# ==========================================================
# ROUTER
# ==========================================================

router = APIRouter(
    prefix="/api/reviews",
    tags=["Reviews"]
)


# ==========================================================
# HEALTH CHECK
# ==========================================================

@router.get("/health")
async def review_health():
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

        company_query = await db.execute(
            select(Company).where(Company.id == company_id)
        )

        company = company_query.scalar_one_or_none()

        if not company:
            raise HTTPException(
                status_code=404,
                detail="Company not found"
            )

        reviews_query = await db.execute(
            select(Review)
            .where(Review.company_id == company_id)
            .order_by(Review.review_date.desc())
        )

        reviews = reviews_query.scalars().all()

        response = []

        for review in reviews:

            response.append({
                "id": review.id,
                "reviewer_name": review.reviewer_name,
                "rating": review.rating,
                "review_text": review.review_text,
                "review_date": review.review_date,
                "sentiment": getattr(review, "sentiment", None),
                "source": getattr(review, "source", "Google"),
                "created_at": review.created_at
            })

        logger.info(f"📊 TOTAL REVIEWS => {len(response)}")

        return {
            "success": True,
            "company_id": company_id,
            "company_name": company.name,
            "total_reviews": len(response),
            "reviews": response
        }

    except HTTPException:
        raise

    except Exception as e:
        logger.exception("❌ GET REVIEWS ERROR")

        raise HTTPException(
            status_code=500,
            detail=str(e)
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

        logger.info(f"🚀 STARTING REVIEW SYNC => {company_id}")

        # ==================================================
        # GET COMPANY
        # ==================================================

        company_query = await db.execute(
            select(Company).where(Company.id == company_id)
        )

        company = company_query.scalar_one_or_none()

        if not company:

            logger.error("❌ COMPANY NOT FOUND")

            raise HTTPException(
                status_code=404,
                detail="Company not found"
            )

        logger.success(f"✅ COMPANY FOUND => {company.name}")

        # ==================================================
        # SCRAPE REVIEWS
        # ==================================================

        reviews = await scrape_google_reviews(
            company_name=company.name,
            google_maps_url=company.google_maps_url
        )

        if not reviews:

            logger.warning("⚠️ NO REVIEWS SCRAPED")

            return {
                "success": False,
                "message": "No reviews found",
                "inserted": 0
            }

        logger.success(f"✅ SCRAPED REVIEWS => {len(reviews)}")

        # ==================================================
        # SAVE REVIEWS
        # ==================================================

        inserted_count = 0

        for item in reviews:

            try:

                review_text = item.get("review_text", "")

                # ==========================================
                # CHECK DUPLICATE
                # ==========================================

                duplicate_query = await db.execute(
                    select(Review).where(
                        Review.company_id == company_id,
                        Review.review_text == review_text
                    )
                )

                duplicate = duplicate_query.scalar_one_or_none()

                if duplicate:
                    continue

                # ==========================================
                # CREATE REVIEW
                # ==========================================

                new_review = Review(
                    company_id=company_id,
                    reviewer_name=item.get(
                        "reviewer_name",
                        "Anonymous"
                    ),
                    rating=float(item.get("rating", 5)),
                    review_text=review_text,
                    review_date=item.get(
                        "review_date",
                        datetime.utcnow()
                    ),
                    source="Google",
                    created_at=datetime.utcnow()
                )

                db.add(new_review)

                inserted_count += 1

            except Exception as inner_error:

                logger.exception(
                    f"❌ REVIEW INSERT ERROR => {inner_error}"
                )

                continue

        # ==================================================
        # COMMIT
        # ==================================================

        await db.commit()

        logger.success(
            f"✅ INSERTED REVIEWS => {inserted_count}"
        )

        # ==================================================
        # TOTAL REVIEWS
        # ==================================================

        total_query = await db.execute(
            select(func.count(Review.id)).where(
                Review.company_id == company_id
            )
        )

        total_reviews = total_query.scalar()

        logger.info(
            f"📊 TOTAL DATABASE REVIEWS => {total_reviews}"
        )

        return {
            "success": True,
            "company_id": company_id,
            "company_name": company.name,
            "scraped_reviews": len(reviews),
            "inserted_reviews": inserted_count,
            "total_reviews": total_reviews
        }

    except HTTPException:
        raise

    except Exception as e:

        logger.exception("❌ REVIEW SYNC ERROR")

        await db.rollback()

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


# ==========================================================
# DELETE REVIEWS
# ==========================================================

@router.delete("/company/{company_id}")
async def delete_company_reviews(
    company_id: int,
    db: AsyncSession = Depends(get_db)
):

    try:

        reviews_query = await db.execute(
            select(Review).where(
                Review.company_id == company_id
            )
        )

        reviews = reviews_query.scalars().all()

        deleted_count = 0

        for review in reviews:
            await db.delete(review)
            deleted_count += 1

        await db.commit()

        logger.success(
            f"🗑️ DELETED REVIEWS => {deleted_count}"
        )

        return {
            "success": True,
            "deleted_reviews": deleted_count
        }

    except Exception as e:

        logger.exception("❌ DELETE REVIEWS ERROR")

        await db.rollback()

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )
