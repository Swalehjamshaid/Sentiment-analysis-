# =========================================================
# FILE: review_saas/app/routes/reviews.py
# =========================================================

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    BackgroundTasks
)

from sqlalchemy.orm import Session
from sqlalchemy import desc, func, and_

from typing import Optional
from datetime import datetime

import logging
import traceback

# =========================================================
# DEBUG
# =========================================================

print("🔥 ACTIVE REVIEWS.PY LOADED 🔥")

# =========================================================
# DATABASE
# =========================================================

from app.database import get_db

# =========================================================
# MODELS
# =========================================================

from app.models import (
    Company,
    Review
)

# =========================================================
# AUTH
# =========================================================

from app.auth import get_current_user

# =========================================================
# SCRAPER IMPORT
# =========================================================

try:

    from app.scraper import scrape_google_reviews

    print("✅ SCRAPER IMPORT SUCCESS")

except Exception as scraper_error:

    scrape_google_reviews = None

    print(
        f"❌ SCRAPER IMPORT FAILED: {scraper_error}"
    )

# =========================================================
# LOGGER
# =========================================================

logger = logging.getLogger(__name__)

# =========================================================
# ROUTER
# =========================================================

router = APIRouter(
    prefix="/api/reviews",
    tags=["Reviews"]
)

# =========================================================
# HEALTH ROUTE
# =========================================================

@router.get("/health")
async def review_health():

    return {
        "success": True,
        "message": "reviews.py working",
        "timestamp": datetime.utcnow()
    }

# =========================================================
# TEST ROUTE
# =========================================================


@router.get("/test-sync")
async def test_sync():

    return {
        "success": True,
        "message": "SYNC ROUTE REGISTERED"
    }

# =========================================================
# DEBUG ROUTES
# =========================================================

@router.get("/debug/routes")
async def debug_routes():

    return {
        "success": True,
        "routes": [
            "GET /api/reviews/health",
            "GET /api/reviews/company/{company_id}",
            "POST /api/reviews/sync/{company_id}",
            "GET /api/reviews/analytics/{company_id}",
            "GET /api/reviews/latest/{company_id}",
            "DELETE /api/reviews/delete/{review_id}",
            "GET /api/reviews/stats/{company_id}"
        ]
    }

# =========================================================
# GET COMPANY REVIEWS
# =========================================================

@router.get("/company/{company_id}")
async def get_company_reviews(
    company_id: int,
    limit: int = Query(100, ge=1, le=1000),
    skip: int = Query(0, ge=0),
    rating: Optional[int] = None,
    sentiment: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):

    try:

        logger.info(
            f"FETCHING REVIEWS => COMPANY {company_id}"
        )

        company = db.query(Company).filter(
            Company.id == company_id
        ).first()

        if not company:

            raise HTTPException(
                status_code=404,
                detail="Company not found"
            )

        query = db.query(Review).filter(
            Review.company_id == company_id
        )

        if rating:

            query = query.filter(
                Review.rating == rating
            )

        if sentiment:

            query = query.filter(
                func.lower(Review.sentiment)
                == sentiment.lower()
            )

        total_reviews = query.count()

        reviews = query.order_by(
            desc(Review.created_at)
        ).offset(skip).limit(limit).all()

        response_reviews = []

        for review in reviews:

            response_reviews.append({

                "id": review.id,

                "company_id": review.company_id,

                "author": review.author,

                "rating": review.rating,

                "review_text": review.review_text,

                "sentiment": review.sentiment,

                "source": review.source,

                "review_date": review.review_date,

                "created_at": review.created_at
            })

        logger.info(
            f"REVIEWS FETCHED => {len(response_reviews)}"
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
            f"GET REVIEWS ERROR => {e}"
        )

        logger.error(traceback.format_exc())

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

# =========================================================
# SYNC ROUTE
# =========================================================

print("🔥 SYNC ROUTE REGISTERED 🔥")

@router.post("/sync/{company_id}")
async def sync_reviews(
    company_id: int,
    background_tasks: BackgroundTasks,
    force_refresh: bool = False,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):

    print("🚀 SYNC ROUTE EXECUTED")

    try:

        logger.info(
            f"SYNC STARTED => COMPANY {company_id}"
        )

        # =================================================
        # COMPANY VALIDATION
        # =================================================

        company = db.query(Company).filter(
            Company.id == company_id
        ).first()

        if not company:

            raise HTTPException(
                status_code=404,
                detail="Company not found"
            )

        # =================================================
        # GOOGLE PLACE ID
        # =================================================

        google_place_id = getattr(
            company,
            "google_place_id",
            None
        )

        if not google_place_id:

            return {
                "success": False,
                "message": "Google Place ID missing",
                "company_id": company_id
            }

        # =================================================
        # SCRAPER VALIDATION
        # =================================================

        if scrape_google_reviews is None:

            return {
                "success": False,
                "message": "scraper.py import failed"
            }

        # =================================================
        # SCRAPE REVIEWS
        # =================================================

        logger.info(
            f"SCRAPING GOOGLE REVIEWS => {google_place_id}"
        )

        scraped_reviews = scrape_google_reviews(
            google_place_id
        )

        print(
            f"SCRAPED REVIEWS COUNT => {len(scraped_reviews)}"
        )

        if not scraped_reviews:

            return {
                "success": False,
                "message": "No reviews fetched",
                "inserted_reviews": 0
            }

        inserted_reviews = 0
        duplicate_reviews = 0
        failed_reviews = 0

        # =================================================
        # INSERT REVIEWS
        # =================================================

        for item in scraped_reviews:

            try:

                review_text = (
                    item.get("review_text", "")
                    .strip()
                )

                if not review_text:
                    continue

                author = item.get(
                    "author",
                    "Anonymous"
                )

                existing_review = db.query(Review).filter(
                    and_(
                        Review.company_id == company_id,
                        Review.review_text == review_text,
                        Review.author == author
                    )
                ).first()

                if existing_review:

                    duplicate_reviews += 1
                    continue

                review = Review(

                    company_id=company_id,

                    author=author,

                    rating=item.get(
                        "rating",
                        0
                    ),

                    review_text=review_text,

                    sentiment=item.get(
                        "sentiment",
                        "neutral"
                    ),

                    source=item.get(
                        "source",
                        "Google"
                    ),

                    review_date=item.get(
                        "review_date",
                        datetime.utcnow()
                    ),

                    created_at=datetime.utcnow()
                )

                db.add(review)

                inserted_reviews += 1

            except Exception as review_error:

                failed_reviews += 1

                logger.error(
                    f"REVIEW INSERT ERROR => {review_error}"
                )

        # =================================================
        # COMMIT
        # =================================================

        db.commit()

        logger.info(
            f"""
            REVIEW SYNC COMPLETE

            COMPANY: {company_id}
            INSERTED: {inserted_reviews}
            DUPLICATES: {duplicate_reviews}
            FAILED: {failed_reviews}
            TOTAL SCRAPED: {len(scraped_reviews)}
            """
        )

        return {

            "success": True,

            "message": "Review sync completed",

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

        db.rollback()

        logger.error(
            f"SYNC ERROR => {e}"
        )

        logger.error(traceback.format_exc())

        raise HTTPException(
            status_code=500,
            detail=f"Review sync failed: {str(e)}"
        )

# =========================================================
# ANALYTICS
# =========================================================

@router.get("/analytics/{company_id}")
async def review_analytics(
    company_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):

    try:

        reviews = db.query(Review).filter(
            Review.company_id == company_id
        ).all()

        total_reviews = len(reviews)

        if total_reviews == 0:

            return {
                "success": True,
                "total_reviews": 0,
                "average_rating": 0
            }

        average_rating = round(
            sum([r.rating for r in reviews])
            / total_reviews,
            2
        )

        return {

            "success": True,

            "company_id": company_id,

            "total_reviews": total_reviews,

            "average_rating": average_rating
        }

    except Exception as e:

        logger.error(
            f"ANALYTICS ERROR => {e}"
        )

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

# =========================================================
# LATEST REVIEWS
# =========================================================

@router.get("/latest/{company_id}")
async def latest_reviews(
    company_id: int,
    limit: int = 10,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):

    try:

        reviews = db.query(Review).filter(
            Review.company_id == company_id
        ).order_by(
            desc(Review.created_at)
        ).limit(limit).all()

        return {

            "success": True,

            "reviews": [

                {
                    "id": r.id,
                    "author": r.author,
                    "rating": r.rating,
                    "review_text": r.review_text,
                    "sentiment": r.sentiment,
                    "review_date": r.review_date
                }

                for r in reviews
            ]
        }

    except Exception as e:

        logger.error(
            f"LATEST REVIEWS ERROR => {e}"
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
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):

    try:

        review = db.query(Review).filter(
            Review.id == review_id
        ).first()

        if not review:

            raise HTTPException(
                status_code=404,
                detail="Review not found"
            )

        db.delete(review)

        db.commit()

        return {
            "success": True,
            "message": "Review deleted"
        }

    except HTTPException:
        raise

    except Exception as e:

        db.rollback()

        logger.error(
            f"DELETE REVIEW ERROR => {e}"
        )

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

# =========================================================
# REVIEW STATS
# =========================================================

@router.get("/stats/{company_id}")
async def review_stats(
    company_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):

    try:

        total_reviews = db.query(Review).filter(
            Review.company_id == company_id
        ).count()

        avg_rating = db.query(
            func.avg(Review.rating)
        ).filter(
            Review.company_id == company_id
        ).scalar()

        return {

            "success": True,

            "company_id": company_id,

            "total_reviews": total_reviews,

            "average_rating": round(
                avg_rating or 0,
                2
            )
        }

    except Exception as e:

        logger.error(
            f"STATS ERROR => {e}"
        )

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

# =========================================================
# END OF FILE
# =========================================================
