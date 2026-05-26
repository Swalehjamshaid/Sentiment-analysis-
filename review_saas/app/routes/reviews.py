# =========================================================
# FILE: app/routes/reviews.py
# TRUSTLYTICS AI - FULL ASYNC ENTERPRISE VERSION
# =========================================================

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query
)

from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import (
    select,
    desc,
    and_,
    func
)

from typing import Optional

from datetime import datetime

import traceback
import logging
import hashlib
import inspect

# =========================================================
# DATABASE
# =========================================================

from app.core.db import get_db

# =========================================================
# MODELS
# =========================================================

from app.core.models import (
    Company,
    Review
)

# =========================================================
# SCRAPER IMPORT
# =========================================================

SCRAPER_AVAILABLE = False

try:

    from app.scraper import scrape_google_reviews

    SCRAPER_AVAILABLE = True

    print("✅ SCRAPER IMPORTED SUCCESSFULLY")

except Exception as scraper_error:

    scrape_google_reviews = None

    print(
        f"❌ SCRAPER IMPORT FAILED => {scraper_error}"
    )

# =========================================================
# LOGGER
# =========================================================

logger = logging.getLogger(__name__)

logger.setLevel(logging.INFO)

print("✅ REVIEWS LOGGER READY")

# =========================================================
# ROUTER
# =========================================================

router = APIRouter(

    prefix="/api/reviews",

    tags=["Reviews"]
)

print("✅ REVIEWS ROUTER LOADED")

# =========================================================
# HELPERS
# =========================================================

def serialize_datetime(value):

    if value is None:
        return None

    if isinstance(value, datetime):
        return value.isoformat()

    return value


def generate_google_review_id(
    company_id: int,
    author: str,
    review_text: str
):

    raw_value = f"{company_id}:{author}:{review_text}"

    return hashlib.sha256(
        raw_value.encode("utf-8")
    ).hexdigest()


async def run_scraper(
    google_place_id: str
):

    if scrape_google_reviews is None:
        return []

    result = scrape_google_reviews(
        google_place_id
    )

    if inspect.isawaitable(result):
        result = await result

    return result or []


# =========================================================
# HEALTH ROUTE
# =========================================================

@router.get("/health")
async def reviews_health():

    return {

        "success": True,

        "service": "reviews",

        "status": "healthy",

        "scraper_available": SCRAPER_AVAILABLE,

        "timestamp": datetime.utcnow().isoformat()
    }

# =========================================================
# TEST ROUTE
# =========================================================

@router.get("/test-sync")
async def test_sync():

    return {

        "success": True,

        "message": "TEST ROUTE WORKING",

        "scraper_available": SCRAPER_AVAILABLE
    }

# =========================================================
# DEBUG ROUTES
# =========================================================

@router.get("/debug/routes")
async def debug_routes():

    return {

        "success": True,

        "routes": [

            "/api/reviews/health",

            "/api/reviews/test-sync",

            "/api/reviews/company/{company_id}",

            "/api/reviews/sync/{company_id}",

            "/api/reviews/analytics/{company_id}",

            "/api/reviews/delete/{review_id}"
        ]
    }

# =========================================================
# GET COMPANY REVIEWS
# =========================================================

@router.get("/company/{company_id}")
async def get_company_reviews(

    company_id: int,

    limit: int = Query(
        100,
        ge=1,
        le=1000
    ),

    skip: int = Query(
        0,
        ge=0
    ),

    rating: Optional[int] = Query(
        None,
        ge=1,
        le=5
    ),

    db: AsyncSession = Depends(get_db)
):

    try:

        logger.info(
            f"📊 FETCHING REVIEWS => {company_id}"
        )

        company_result = await db.execute(

            select(Company).where(
                Company.id == company_id
            )
        )

        company = company_result.scalar_one_or_none()

        if not company:

            raise HTTPException(

                status_code=404,

                detail="Company not found"
            )

        query = select(Review).where(
            Review.company_id == company_id
        )

        count_query = select(
            func.count(Review.id)
        ).where(
            Review.company_id == company_id
        )

        if rating is not None:

            query = query.where(
                Review.rating == rating
            )

            count_query = count_query.where(
                Review.rating == rating
            )

        total_result = await db.execute(
            count_query
        )

        total_reviews = total_result.scalar() or 0

        reviews_result = await db.execute(

            query.order_by(
                desc(Review.created_at)
            ).offset(skip).limit(limit)
        )

        reviews = reviews_result.scalars().all()

        response_reviews = []

        for review in reviews:

            response_reviews.append({

                "id": review.id,

                "company_id": review.company_id,

                "author": review.author_name,

                "rating": review.rating,

                "content": review.text,

                "review_text": review.text,

                "sentiment_score":
                    review.sentiment_score,

                "google_review_time":
                    serialize_datetime(
                        review.google_review_time
                    ),

                "created_at":
                    serialize_datetime(
                        review.created_at
                    )
            })

        logger.info(
            f"✅ REVIEWS FETCHED => {len(response_reviews)}"
        )

        return {

            "success": True,

            "company_id": company_id,

            "company_name": company.name,

            "total_reviews": total_reviews,

            "reviews": response_reviews
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

        raise HTTPException(

            status_code=500,

            detail=str(e)
        )

# =========================================================
# SYNC REVIEWS
# =========================================================

@router.post("/sync/{company_id}")
@router.post("/sync/{company_id}/")
async def sync_reviews(

    company_id: int,

    db: AsyncSession = Depends(get_db)
):

    try:

        logger.info(
            f"🚀 SYNC STARTED => {company_id}"
        )

        company_result = await db.execute(

            select(Company).where(
                Company.id == company_id
            )
        )

        company = company_result.scalar_one_or_none()

        if not company:

            raise HTTPException(

                status_code=404,

                detail="Company not found"
            )

        if not SCRAPER_AVAILABLE:

            return {

                "success": False,

                "message":
                    "scraper.py import failed",

                "company_id": company_id
            }

        google_place_id = getattr(
            company,
            "google_place_id",
            None
        )

        if not google_place_id:

            return {

                "success": False,

                "message":
                    "Google Place ID missing",

                "company_id": company_id
            }

        logger.info(
            f"🌍 SCRAPING REVIEWS => {google_place_id}"
        )

        scraped_reviews = await run_scraper(
            google_place_id
        )

        if not scraped_reviews:

            return {

                "success": False,

                "message":
                    "No reviews fetched",

                "company_id": company_id,

                "inserted_reviews": 0
            }

        inserted_reviews = 0
        duplicate_reviews = 0
        failed_reviews = 0

        for item in scraped_reviews:

            try:

                review_text = str(

                    item.get(
                        "review_text",

                        item.get(
                            "content",
                            ""
                        )
                    )

                ).strip()

                if not review_text:

                    failed_reviews += 1

                    continue

                author = str(
                    item.get(
                        "author",
                        "Anonymous"
                    )
                ).strip() or "Anonymous"

                try:

                    rating = int(
                        item.get(
                            "rating",
                            0
                        )
                    )

                except Exception:

                    rating = 0

                if rating < 0:
                    rating = 0

                if rating > 5:
                    rating = 5

                duplicate_result = await db.execute(

                    select(Review).where(

                        and_(

                            Review.company_id
                            == company_id,

                            Review.text
                            == review_text,

                            Review.author_name
                            == author
                        )
                    )
                )

                existing_review = (
                    duplicate_result
                    .scalar_one_or_none()
                )

                if existing_review:

                    duplicate_reviews += 1

                    continue

                review = Review(

                    company_id=company_id,

                    google_review_id=
                        generate_google_review_id(
                            company_id,
                            author,
                            review_text
                        ),

                    author_name=author,

                    rating=rating,

                    text=review_text,

                    sentiment_score=0.5,

                    google_review_time=datetime.utcnow(),

                    created_at=datetime.utcnow()
                )

                db.add(review)

                inserted_reviews += 1

            except Exception as review_error:

                failed_reviews += 1

                logger.error(
                    f"❌ REVIEW INSERT ERROR => {review_error}"
                )

                logger.error(
                    traceback.format_exc()
                )

        await db.commit()

        logger.info(
            f"✅ SYNC COMPLETE => {inserted_reviews}"
        )

        return {

            "success": True,

            "message":
                "Reviews synced successfully",

            "company_id": company_id,

            "company_name": company.name,

            "inserted_reviews": inserted_reviews,

            "duplicate_reviews": duplicate_reviews,

            "failed_reviews": failed_reviews,

            "total_scraped": len(scraped_reviews)
        }

    except HTTPException:
        raise

    except Exception as e:

        await db.rollback()

        logger.error(
            f"❌ SYNC ERROR => {e}"
        )

        logger.error(
            traceback.format_exc()
        )

        raise HTTPException(

            status_code=500,

            detail=str(e)
        )

# =========================================================
# ANALYTICS
# =========================================================

@router.get("/analytics/{company_id}")
async def review_analytics(

    company_id: int,

    db: AsyncSession = Depends(get_db)
):

    try:

        company_result = await db.execute(

            select(Company).where(
                Company.id == company_id
            )
        )

        company = company_result.scalar_one_or_none()

        if not company:

            raise HTTPException(

                status_code=404,

                detail="Company not found"
            )

        result = await db.execute(

            select(Review).where(
                Review.company_id == company_id
            )
        )

        reviews = result.scalars().all()

        total_reviews = len(reviews)

        if total_reviews == 0:

            return {

                "success": True,

                "company_id": company_id,

                "total_reviews": 0,

                "average_rating": 0
            }

        average_rating = round(

            sum([
                review.rating or 0
                for review in reviews
            ]) / total_reviews,

            2
        )

        return {

            "success": True,

            "company_id": company_id,

            "total_reviews": total_reviews,

            "average_rating": average_rating
        }

    except HTTPException:
        raise

    except Exception as e:

        logger.error(
            f"❌ ANALYTICS ERROR => {e}"
        )

        logger.error(
            traceback.format_exc()
        )

        raise HTTPException(

            status_code=500,

            detail=str(e)
        )

# =========================================================
# DELETE REVIEW
# =========================================================

@router.delete("/delete/{review_id}")
async def delete_review(

    review_id: int,

    db: AsyncSession = Depends(get_db)
):

    try:

        result = await db.execute(

            select(Review).where(
                Review.id == review_id
            )
        )

        review = result.scalar_one_or_none()

        if not review:

            raise HTTPException(

                status_code=404,

                detail="Review not found"
            )

        await db.delete(review)

        await db.commit()

        return {

            "success": True,

            "message": "Review deleted",

            "review_id": review_id
        }

    except HTTPException:
        raise

    except Exception as e:

        await db.rollback()

        logger.error(
            f"❌ DELETE REVIEW ERROR => {e}"
        )

        logger.error(
            traceback.format_exc()
        )

        raise HTTPException(

            status_code=500,

            detail=str(e)
        )

# =========================================================
# ROUTER READY
# =========================================================

print("✅ REVIEWS ROUTER FULLY READY")
