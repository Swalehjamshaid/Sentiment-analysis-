from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    BackgroundTasks,
    Query,
    status
)

from sqlalchemy.orm import Session
from sqlalchemy import desc, func, and_, or_

from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import traceback
import logging
import asyncio

# =========================================================
# DATABASE / AUTH IMPORTS
# =========================================================

from database import get_db

from models import (
    Company,
    Review
)

from auth import get_current_user

# =========================================================
# OPTIONAL SCRAPER IMPORTS
# =========================================================

# Your scraper.py should contain:
#
# def scrape_google_reviews(place_id: str):
#     return [...]
#

try:
    from scraper import scrape_google_reviews
except Exception:
    scrape_google_reviews = None

# =========================================================
# LOGGER
# =========================================================

logger = logging.getLogger("review_router")

# =========================================================
# ROUTER
# =========================================================

router = APIRouter(
    prefix="/reviews",
    tags=["Reviews"]
)

# =========================================================
# HEALTH CHECK
# =========================================================

@router.get("/health")
async def review_health_check():

    return {
        "success": True,
        "module": "reviews",
        "status": "healthy",
        "time": datetime.utcnow().isoformat()
    }

# =========================================================
# GET ALL REVIEWS OF COMPANY
# =========================================================

@router.get("/company/{company_id}")
async def get_company_reviews(
    company_id: int,
    limit: int = Query(100, ge=1, le=1000),
    skip: int = Query(0, ge=0),
    sentiment: Optional[str] = None,
    rating: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):

    """
    GET COMPANY REVIEWS
    """

    try:

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

        # =================================================
        # FILTERS
        # =================================================

        if sentiment:

            query = query.filter(
                func.lower(Review.sentiment) == sentiment.lower()
            )

        if rating:

            query = query.filter(
                Review.rating == rating
            )

        total_reviews = query.count()

        reviews = query.order_by(
            desc(Review.review_date),
            desc(Review.created_at)
        ).offset(skip).limit(limit).all()

        response_reviews = []

        for review in reviews:

            response_reviews.append({
                "id": review.id,
                "author": getattr(review, "author", "Anonymous"),
                "rating": getattr(review, "rating", 0),
                "review_text": getattr(review, "review_text", ""),
                "sentiment": getattr(review, "sentiment", "neutral"),
                "review_date": getattr(review, "review_date", None),
                "source": getattr(review, "source", "Google"),
                "created_at": getattr(review, "created_at", None)
            })

        return {
            "success": True,
            "company_id": company.id,
            "company_name": company.name,
            "total_reviews": total_reviews,
            "limit": limit,
            "skip": skip,
            "reviews": response_reviews
        }

    except HTTPException:
        raise

    except Exception as e:

        logger.error(f"GET REVIEWS ERROR: {str(e)}")
        logger.error(traceback.format_exc())

        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch reviews: {str(e)}"
        )

# =========================================================
# MAIN SYNC ROUTE
# THIS FIXES:
#
# POST /api/reviews/sync/18 HTTP/1.1" 404 Not Found
#
# =========================================================

@router.post("/sync/{company_id}")
async def sync_reviews(
    company_id: int,
    background_tasks: BackgroundTasks,
    force_refresh: bool = False,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):

    """
    SYNC GOOGLE REVIEWS

    FRONTEND CALL:
    POST /api/reviews/sync/18

    THIS IS THE EXACT ROUTE YOUR FRONTEND NEEDS
    """

    try:

        logger.info(
            f"SYNC REQUEST RECEIVED FOR COMPANY: {company_id}"
        )

        # =================================================
        # COMPANY VALIDATION
        # =================================================

        company = db.query(Company).filter(
            Company.id == company_id
        ).first()

        if not company:

            logger.error(
                f"COMPANY NOT FOUND: {company_id}"
            )

            raise HTTPException(
                status_code=404,
                detail="Company not found"
            )

        # =================================================
        # GOOGLE PLACE ID VALIDATION
        # =================================================

        google_place_id = getattr(
            company,
            "google_place_id",
            None
        )

        if not google_place_id:

            logger.error(
                f"GOOGLE PLACE ID MISSING FOR COMPANY {company_id}"
            )

            return {
                "success": False,
                "message": "Google Place ID missing",
                "company_id": company_id
            }

        # =================================================
        # SCRAPER VALIDATION
        # =================================================

        if scrape_google_reviews is None:

            logger.error(
                "scrape_google_reviews IMPORT FAILED"
            )

            return {
                "success": False,
                "message": "scraper.py not connected properly",
                "company_id": company_id
            }

        # =================================================
        # START SCRAPING
        # =================================================

        logger.info(
            f"STARTING SCRAPING FOR PLACE ID: {google_place_id}"
        )

        scraped_reviews = scrape_google_reviews(
            google_place_id
        )

        if not scraped_reviews:

            logger.warning(
                "NO REVIEWS RETURNED FROM SCRAPER"
            )

            return {
                "success": False,
                "message": "No reviews fetched",
                "company_id": company_id,
                "inserted_reviews": 0
            }

        inserted_reviews = 0
        duplicate_reviews = 0
        failed_reviews = 0

        # =================================================
        # PROCESS REVIEWS
        # =================================================

        for item in scraped_reviews:

            try:

                review_text = (
                    item.get("review_text", "")
                    .strip()
                )

                if not review_text:
                    continue

                # =========================================
                # DUPLICATE CHECK
                # =========================================

                existing_review = db.query(Review).filter(
                    Review.company_id == company_id,
                    Review.review_text == review_text
                ).first()

                if existing_review:

                    duplicate_reviews += 1
                    continue

                # =========================================
                # CREATE REVIEW OBJECT
                # =========================================

                review = Review(
                    company_id=company_id,
                    author=item.get(
                        "author",
                        "Anonymous"
                    ),
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

            except Exception as inner_error:

                failed_reviews += 1

                logger.error(
                    f"FAILED TO PROCESS REVIEW: {str(inner_error)}"
                )

        # =================================================
        # SAVE CHANGES
        # =================================================

        db.commit()

        logger.info(
            f"""
            REVIEW SYNC COMPLETED
            COMPANY: {company_id}
            INSERTED: {inserted_reviews}
            DUPLICATES: {duplicate_reviews}
            FAILED: {failed_reviews}
            """
        )

        return {
            "success": True,
            "message": "Review sync completed successfully",
            "company_id": company_id,
            "company_name": company.name,
            "inserted_reviews": inserted_reviews,
            "duplicate_reviews": duplicate_reviews,
            "failed_reviews": failed_reviews,
            "total_scraped": len(scraped_reviews),
            "google_place_id": google_place_id
        }

    except HTTPException:
        raise

    except Exception as e:

        db.rollback()

        logger.error(f"SYNC ERROR: {str(e)}")
        logger.error(traceback.format_exc())

        raise HTTPException(
            status_code=500,
            detail=f"Review sync failed: {str(e)}"
        )

# =========================================================
# REVIEW ANALYTICS
# =========================================================

@router.get("/analytics/{company_id}")
async def review_analytics(
    company_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):

    """
    REVIEW ANALYTICS
    """

    try:

        reviews = db.query(Review).filter(
            Review.company_id == company_id
        ).all()

        total_reviews = len(reviews)

        if total_reviews == 0:

            return {
                "success": True,
                "total_reviews": 0,
                "average_rating": 0,
                "positive_reviews": 0,
                "negative_reviews": 0,
                "neutral_reviews": 0,
                "rating_distribution": {}
            }

        average_rating = round(
            sum([r.rating for r in reviews]) / total_reviews,
            2
        )

        positive_reviews = len([
            r for r in reviews
            if getattr(r, "sentiment", "") == "positive"
        ])

        negative_reviews = len([
            r for r in reviews
            if getattr(r, "sentiment", "") == "negative"
        ])

        neutral_reviews = len([
            r for r in reviews
            if getattr(r, "sentiment", "") == "neutral"
        ])

        rating_distribution = {
            "1_star": len([r for r in reviews if r.rating == 1]),
            "2_star": len([r for r in reviews if r.rating == 2]),
            "3_star": len([r for r in reviews if r.rating == 3]),
            "4_star": len([r for r in reviews if r.rating == 4]),
            "5_star": len([r for r in reviews if r.rating == 5]),
        }

        return {
            "success": True,
            "company_id": company_id,
            "total_reviews": total_reviews,
            "average_rating": average_rating,
            "positive_reviews": positive_reviews,
            "negative_reviews": negative_reviews,
            "neutral_reviews": neutral_reviews,
            "rating_distribution": rating_distribution
        }

    except Exception as e:

        logger.error(
            f"ANALYTICS ERROR: {str(e)}"
        )

        raise HTTPException(
            status_code=500,
            detail=f"Analytics failed: {str(e)}"
        )

# =========================================================
# DELETE REVIEW
# =========================================================

@router.delete("/{review_id}")
async def delete_review(
    review_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
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
            "message": "Review deleted successfully"
        }

    except HTTPException:
        raise

    except Exception as e:

        db.rollback()

        logger.error(
            f"DELETE REVIEW ERROR: {str(e)}"
        )

        raise HTTPException(
            status_code=500,
            detail=f"Delete failed: {str(e)}"
        )

# =========================================================
# GET LATEST REVIEWS
# =========================================================

@router.get("/latest/{company_id}")
async def latest_reviews(
    company_id: int,
    limit: int = 10,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):

    try:

        reviews = db.query(Review).filter(
            Review.company_id == company_id
        ).order_by(
            desc(Review.created_at)
        ).limit(limit).all()

        latest_reviews_data = []

        for review in reviews:

            latest_reviews_data.append({
                "id": review.id,
                "author": review.author,
                "rating": review.rating,
                "review_text": review.review_text,
                "sentiment": review.sentiment,
                "review_date": review.review_date
            })

        return {
            "success": True,
            "reviews": latest_reviews_data
        }

    except Exception as e:

        logger.error(
            f"LATEST REVIEW ERROR: {str(e)}"
        )

        raise HTTPException(
            status_code=500,
            detail=f"Latest review fetch failed: {str(e)}"
        )

# =========================================================
# MANUAL TEST ROUTE
# =========================================================

@router.get("/test-sync-route")
async def test_sync_route():

    """
    USE THIS TO VERIFY ROUTE IS ACTIVE
    """

    return {
        "success": True,
        "message": "SYNC ROUTE IS ACTIVE",
        "expected_frontend_route": "/api/reviews/sync/{company_id}",
        "method": "POST"
    }

# =========================================================
# ROUTE DEBUGGING
# =========================================================

@router.get("/debug/routes")
async def debug_routes():

    """
    DEBUG ALL ROUTES
    """

    return {
        "success": True,
        "routes": [
            "GET /reviews/health",
            "GET /reviews/company/{company_id}",
            "POST /reviews/sync/{company_id}",
            "GET /reviews/analytics/{company_id}",
            "GET /reviews/latest/{company_id}",
            "DELETE /reviews/{review_id}",
            "GET /reviews/test-sync-route",
            "GET /reviews/debug/routes"
        ]
    }

# =========================================================
# IMPORTANT MAIN.PY CONFIGURATION
# =========================================================

"""
YOU MUST HAVE THIS IN main.py

-------------------------------------------------

from review import router as review_router

app.include_router(
    review_router,
    prefix="/api"
)

-------------------------------------------------

WITHOUT THIS:

POST /api/reviews/sync/18

WILL RETURN:

404 NOT FOUND

=================================================

FINAL ENDPOINT GENERATED:

/api/reviews/sync/{company_id}

=================================================
"""

# =========================================================
# END OF FILE
# =========================================================
