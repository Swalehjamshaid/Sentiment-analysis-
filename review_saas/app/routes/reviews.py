# ==========================================================
# FILE: app/routes/reviews.py
# TRUSTLYTICS AI
# ENTERPRISE REVIEW ROUTES
# FULLY ALIGNED + STABLE VERSION
# MAY 2026
# ==========================================================

from __future__ import annotations

import logging
import traceback

from datetime import datetime

from fastapi import (
    APIRouter,
    HTTPException,
    Depends,
    Request,
)

from sqlalchemy import (
    select,
    desc,
)

from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

# ==========================================================
# DATABASE
# ==========================================================

from app.core.db import get_db

# ==========================================================
# MODELS
# ==========================================================

from app.core.models import (
    Company,
    Review,
)

# ==========================================================
# SCRAPER
# ==========================================================

from app.scraper import (
    scrape_google_reviews,
)

# ==========================================================
# LOGGER
# ==========================================================

logger = logging.getLogger(__name__)

# ==========================================================
# ROUTER
# ==========================================================

router = APIRouter(

    prefix="/api/reviews",

    tags=["Reviews"]
)

# ==========================================================
# SAFE HELPERS
# ==========================================================

def safe_str(value, default=""):

    try:

        if value is None:
            return default

        return str(value)

    except:
        return default


def safe_int(value, default=0):

    try:

        if value is None:
            return default

        return int(value)

    except:
        return default


def safe_datetime(value):

    try:

        if not value:
            return None

        if isinstance(value, datetime):
            return value

        if isinstance(value, str):

            return datetime.fromisoformat(
                value.replace("Z", "+00:00")
            )

        return None

    except:

        return None

# ==========================================================
# GET REVIEWS
# ==========================================================

@router.get("/company/{company_id}")

async def get_company_reviews(

    company_id: int,

    db: AsyncSession = Depends(get_db)
):

    try:

        logger.info(
            f"📦 FETCHING REVIEWS => {company_id}"
        )

        stmt = (

            select(Review)

            .where(
                Review.company_id == company_id
            )

            .order_by(
                desc(Review.google_review_time)
            )

            .limit(1000)
        )

        result = await db.execute(stmt)

        reviews = result.scalars().all()

        logger.info(
            f"✅ REVIEWS FETCHED => {len(reviews)}"
        )

        return {

            "status": "success",

            "total_reviews": len(reviews),

            "reviews": [

                {

                    "id":
                        review.id,

                    "author":
                        safe_str(
                            review.author_name,
                            "Anonymous"
                        ),

                    "rating":
                        safe_int(
                            review.rating,
                            0
                        ),

                    "content":
                        safe_str(
                            review.text,
                            ""
                        ),

                    "created_at":
                        (
                            review.google_review_time.isoformat()

                            if review.google_review_time

                            else None
                        ),

                    "sentiment_score":
                        review.sentiment_score,

                    "issue_category":
                        review.issue_category,

                    "emotion":
                        review.emotion,

                    "risk_score":
                        review.risk_score,
                }

                for review in reviews
            ]
        }

    except Exception as e:

        logger.error(
            f"❌ GET REVIEWS FAILED => {e}"
        )

        logger.error(
            traceback.format_exc()
        )

        raise HTTPException(

            status_code=500,

            detail=str(e)
        )

# ==========================================================
# SYNC REVIEWS
# ==========================================================

@router.post("/sync/{company_id}")

async def sync_reviews(

    request: Request,

    company_id: int,

    db: AsyncSession = Depends(get_db)
):

    try:

        logger.info(
            f"🚀 REVIEW SYNC STARTED => {company_id}"
        )

        # ==================================================
        # GET COMPANY
        # ==================================================

        company_stmt = (

            select(Company)

            .where(
                Company.id == company_id
            )
        )

        company_result = await db.execute(
            company_stmt
        )

        company = company_result.scalar_one_or_none()

        if not company:

            logger.error(
                f"❌ COMPANY NOT FOUND => {company_id}"
            )

            raise HTTPException(

                status_code=404,

                detail="Company not found"
            )

        logger.info(
            f"🏢 COMPANY => {company.name}"
        )

        # ==================================================
        # EXISTING REVIEWS
        # ==================================================

        existing_stmt = (

            select(
                Review.google_review_id
            )

            .where(
                Review.company_id == company_id
            )
        )

        existing_result = await db.execute(
            existing_stmt
        )

        existing_ids = set(

            existing_result.scalars().all()
        )

        logger.info(
            f"📦 EXISTING IDS => {len(existing_ids)}"
        )

        # ==================================================
        # SCRAPE REVIEWS
        # ==================================================

        scraped_reviews = await scrape_google_reviews(

            place_id=company.google_place_id,

            existing_ids=existing_ids,

            target_limit=300
        )

        logger.info(
            f"✅ SCRAPED REVIEWS => {len(scraped_reviews)}"
        )

        # ==================================================
        # NO REVIEWS
        # ==================================================

        if not scraped_reviews:

            return {

                "status": "success",

                "company_id": company_id,

                "company_name": company.name,

                "reviews_collected": 0,

                "message":
                    "No new reviews found"
            }

        # ==================================================
        # SAVE REVIEWS
        # ==================================================

        inserted_count = 0

        skipped_count = 0

        for item in scraped_reviews:

            try:

                review_id = safe_str(
                    item.get("review_id")
                )

                if not review_id:

                    skipped_count += 1

                    continue

                if review_id in existing_ids:

                    skipped_count += 1

                    continue

                review_text = safe_str(
                    item.get("text")
                )

                if not review_text:

                    skipped_count += 1

                    continue

                review_date = safe_datetime(
                    item.get("date")
                )

                if not review_date:

                    review_date = datetime.utcnow()

                review = Review(

                    company_id=company.id,

                    google_review_id=review_id,

                    author_name=safe_str(
                        item.get(
                            "author",
                            "Anonymous"
                        )
                    ),

                    rating=safe_int(
                        item.get(
                            "rating",
                            5
                        ),
                        5
                    ),

                    text=review_text,

                    google_review_time=review_date,

                    first_seen_at=datetime.utcnow(),

                    review_likes=0,

                    created_at=datetime.utcnow(),

                    sentiment_score=0,

                    issue_category=None,

                    emotion=None,

                    urgency_score=0,

                    ai_summary=None,

                    risk_score=0,

                    topic_cluster=None,
                )

                db.add(review)

                inserted_count += 1

            except Exception as review_error:

                skipped_count += 1

                logger.warning(
                    f"⚠️ REVIEW INSERT FAILED => {review_error}"
                )

        # ==================================================
        # COMMIT
        # ==================================================

        await db.commit()

        logger.info(
            f"✅ DATABASE COMMIT SUCCESS"
        )

        logger.info(
            f"✅ INSERTED => {inserted_count}"
        )

        logger.info(
            f"⚠️ SKIPPED => {skipped_count}"
        )

        # ==================================================
        # FINAL RESPONSE
        # ==================================================

        return {

            "status": "success",

            "company_id":
                company.id,

            "company_name":
                company.name,

            "reviews_collected":
                inserted_count,

            "skipped_reviews":
                skipped_count,

            "total_scraped":
                len(scraped_reviews),

            "message":
                f"{inserted_count} reviews synced successfully"
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

        try:
            await db.rollback()

        except:
            pass

        raise HTTPException(

            status_code=500,

            detail=str(e)
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

        stmt = (

            select(Review)

            .where(
                Review.id == review_id
            )
        )

        result = await db.execute(stmt)

        review = result.scalar_one_or_none()

        if not review:

            raise HTTPException(

                status_code=404,

                detail="Review not found"
            )

        await db.delete(review)

        await db.commit()

        logger.info(
            f"🗑 REVIEW DELETED => {review_id}"
        )

        return {

            "status": "success",

            "message":
                "Review deleted successfully"
        }

    except HTTPException:

        raise

    except Exception as e:

        logger.error(
            f"❌ DELETE FAILED => {e}"
        )

        logger.error(
            traceback.format_exc()
        )

        await db.rollback()

        raise HTTPException(

            status_code=500,

            detail=str(e)
        )

# ==========================================================
# HEALTH CHECK
# ==========================================================

@router.get("/health")

async def reviews_health():

    return {

        "status": "healthy",

        "service": "reviews",

        "version": "2026.05.enterprise"
    }
