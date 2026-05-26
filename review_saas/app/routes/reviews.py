# =========================================================
# FILE: review_saas/app/routes/reviews.py
# TRUSTLYTICS AI - REVIEWS ROUTES
# =========================================================

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_, or_, func
from typing import Optional, Any
from datetime import datetime
import hashlib
import inspect
import logging
import traceback

from app.core.db import get_db
from app.core.models import Company, Review

# =========================================================
# SCRAPER IMPORT
# =========================================================

SCRAPER_AVAILABLE = False
scrape_google_reviews = None

try:
    from app.scraper import scrape_google_reviews

    SCRAPER_AVAILABLE = True
except Exception as scraper_error:
    print(f"SCRAPER IMPORT FAILED => {scraper_error}")

# =========================================================
# LOGGER
# =========================================================

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# =========================================================
# ROUTER
# =========================================================

router = APIRouter(
    prefix="/api/reviews",
    tags=["Reviews"],
)

# =========================================================
# HELPERS
# =========================================================

def safe_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except Exception:
        return default


def clamp_rating(value: Any) -> int:
    rating = safe_int(value, 0)
    if rating < 0:
        return 0
    if rating > 5:
        return 5
    return rating


def make_google_review_id(company_id: int, author: str, review_text: str) -> str:
    raw = f"{company_id}:{author}:{review_text}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def normalize_scraper_response(scraped_data: Any) -> list:
    """
    Supports scraper output as:
    - list[dict]
    - {"reviews": list[dict]}
    - {"data": list[dict]}
    - {"success": true, "reviews": list[dict]}
    """

    if scraped_data is None:
        return []

    if isinstance(scraped_data, list):
        return scraped_data

    if isinstance(scraped_data, dict):
        for key in ("reviews", "data", "items", "results"):
            value = scraped_data.get(key)
            if isinstance(value, list):
                return value

    return []


def serialize_review(review: Review) -> dict:
    return {
        "id": review.id,
        "company_id": review.company_id,
        "google_review_id": review.google_review_id,
        "author": review.author_name,
        "author_name": review.author_name,
        "rating": review.rating,
        "content": review.text,
        "review_text": review.text,
        "sentiment_score": review.sentiment_score,
        "google_review_time": review.google_review_time,
        "created_at": review.created_at,
    }

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
        "timestamp": datetime.utcnow().isoformat(),
    }

# =========================================================
# TEST ROUTE
# =========================================================

@router.get("/test-sync")
async def test_sync():
    return {
        "success": True,
        "message": "TEST ROUTE WORKING",
        "scraper_available": SCRAPER_AVAILABLE,
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
            "/api/reviews/debug/routes",
            "/api/reviews/company/{company_id}",
            "/api/reviews/sync/{company_id}",
            "/api/reviews/analytics/{company_id}",
            "/api/reviews/delete/{review_id}",
        ],
    }

# =========================================================
# GET COMPANY REVIEWS
# =========================================================

@router.get("/company/{company_id}")
async def get_company_reviews(
    company_id: int,
    limit: int = Query(100, ge=1, le=1000),
    skip: int = Query(0, ge=0),
    rating: Optional[int] = Query(None, ge=1, le=5),
    db: Session = Depends(get_db),
):
    try:
        company = db.query(Company).filter(Company.id == company_id).first()

        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        query = db.query(Review).filter(Review.company_id == company_id)

        if rating is not None:
            query = query.filter(Review.rating == rating)

        total_reviews = query.count()

        reviews = (
            query.order_by(desc(Review.created_at))
            .offset(skip)
            .limit(limit)
            .all()
        )

        return {
            "success": True,
            "company_id": company_id,
            "company_name": company.name,
            "total_reviews": total_reviews,
            "limit": limit,
            "skip": skip,
            "reviews": [serialize_review(review) for review in reviews],
        }

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"GET REVIEWS ERROR => {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

# =========================================================
# SYNC REVIEWS
# =========================================================

@router.post("/sync/{company_id}")
@router.post("/sync/{company_id}/")
async def sync_reviews(
    company_id: int,
    db: Session = Depends(get_db),
):
    try:
        logger.info(f"SYNC STARTED => company_id={company_id}")

        company = db.query(Company).filter(Company.id == company_id).first()

        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        if not SCRAPER_AVAILABLE or scrape_google_reviews is None:
            return {
                "success": False,
                "message": "scraper.py import failed or scraper unavailable",
                "company_id": company_id,
                "inserted_reviews": 0,
                "duplicate_reviews": 0,
                "failed_reviews": 0,
                "total_scraped": 0,
            }

        google_place_id = safe_str(getattr(company, "google_place_id", None))

        if not google_place_id:
            return {
                "success": False,
                "message": "Google Place ID missing",
                "company_id": company_id,
                "inserted_reviews": 0,
                "duplicate_reviews": 0,
                "failed_reviews": 0,
                "total_scraped": 0,
            }

        logger.info(f"SCRAPING GOOGLE REVIEWS => {google_place_id}")

        try:
            scraper_result = scrape_google_reviews(google_place_id)

            if inspect.isawaitable(scraper_result):
                scraper_result = await scraper_result

        except Exception as scraper_error:
            logger.error(f"SCRAPER ERROR => {scraper_error}")
            logger.error(traceback.format_exc())

            return {
                "success": False,
                "message": "Google reviews scraper failed",
                "error": str(scraper_error),
                "company_id": company_id,
                "inserted_reviews": 0,
                "duplicate_reviews": 0,
                "failed_reviews": 0,
                "total_scraped": 0,
            }

        scraped_reviews = normalize_scraper_response(scraper_result)

        if not scraped_reviews:
            return {
                "success": False,
                "message": "No reviews fetched",
                "company_id": company_id,
                "company_name": company.name,
                "inserted_reviews": 0,
                "duplicate_reviews": 0,
                "failed_reviews": 0,
                "total_scraped": 0,
            }

        inserted_reviews = 0
        duplicate_reviews = 0
        failed_reviews = 0

        for item in scraped_reviews:
            try:
                if not isinstance(item, dict):
                    failed_reviews += 1
                    continue

                review_text = safe_str(
                    item.get("review_text")
                    or item.get("content")
                    or item.get("text")
                    or item.get("review")
                )

                if not review_text:
                    failed_reviews += 1
                    continue

                author = safe_str(
                    item.get("author")
                    or item.get("author_name")
                    or item.get("name"),
                    "Anonymous",
                )

                if not author:
                    author = "Anonymous"

                rating = clamp_rating(
                    item.get("rating")
                    or item.get("stars")
                    or item.get("score")
                )

                google_review_id = safe_str(
                    item.get("google_review_id")
                    or item.get("review_id")
                    or item.get("id")
                )

                if not google_review_id:
                    google_review_id = make_google_review_id(
                        company_id=company_id,
                        author=author,
                        review_text=review_text,
                    )

                existing_review = (
                    db.query(Review)
                    .filter(
                        Review.company_id == company_id,
                        or_(
                            Review.google_review_id == google_review_id,
                            and_(
                                Review.text == review_text,
                                Review.author_name == author,
                            ),
                        ),
                    )
                    .first()
                )

                if existing_review:
                    duplicate_reviews += 1
                    continue

                review_time = item.get("google_review_time") or item.get("created_at")

                if isinstance(review_time, datetime):
                    google_review_time = review_time
                else:
                    google_review_time = datetime.utcnow()

                sentiment_score = item.get("sentiment_score", 0.5)

                try:
                    sentiment_score = float(sentiment_score)
                except Exception:
                    sentiment_score = 0.5

                review = Review(
                    company_id=company_id,
                    google_review_id=google_review_id,
                    author_name=author,
                    rating=rating,
                    text=review_text,
                    sentiment_score=sentiment_score,
                    google_review_time=google_review_time,
                    created_at=datetime.utcnow(),
                )

                db.add(review)
                inserted_reviews += 1

            except Exception as review_error:
                failed_reviews += 1
                logger.error(f"REVIEW INSERT ERROR => {review_error}")
                logger.error(traceback.format_exc())

        try:
            db.commit()
        except Exception as commit_error:
            db.rollback()
            logger.error(f"DATABASE COMMIT ERROR => {commit_error}")
            logger.error(traceback.format_exc())

            raise HTTPException(
                status_code=500,
                detail=f"Database commit failed: {commit_error}",
            )

        logger.info(
            f"SYNC COMPLETE => inserted={inserted_reviews}, "
            f"duplicates={duplicate_reviews}, failed={failed_reviews}"
        )

        return {
            "success": True,
            "message": "Reviews synced successfully",
            "company_id": company_id,
            "company_name": company.name,
            "inserted_reviews": inserted_reviews,
            "duplicate_reviews": duplicate_reviews,
            "failed_reviews": failed_reviews,
            "total_scraped": len(scraped_reviews),
        }

    except HTTPException:
        raise

    except Exception as e:
        db.rollback()
        logger.error(f"SYNC ERROR => {e}")
        logger.error(traceback.format_exc())

        raise HTTPException(status_code=500, detail=str(e))

# =========================================================
# ANALYTICS
# =========================================================

@router.get("/analytics/{company_id}")
async def review_analytics(
    company_id: int,
    db: Session = Depends(get_db),
):
    try:
        company = db.query(Company).filter(Company.id == company_id).first()

        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        total_reviews = (
            db.query(func.count(Review.id))
            .filter(Review.company_id == company_id)
            .scalar()
            or 0
        )

        if total_reviews == 0:
            return {
                "success": True,
                "company_id": company_id,
                "company_name": company.name,
                "total_reviews": 0,
                "average_rating": 0,
                "rating_breakdown": {
                    "1": 0,
                    "2": 0,
                    "3": 0,
                    "4": 0,
                    "5": 0,
                },
            }

        average_rating = (
            db.query(func.avg(Review.rating))
            .filter(Review.company_id == company_id)
            .scalar()
            or 0
        )

        rating_rows = (
            db.query(Review.rating, func.count(Review.id))
            .filter(Review.company_id == company_id)
            .group_by(Review.rating)
            .all()
        )

        rating_breakdown = {
            "1": 0,
            "2": 0,
            "3": 0,
            "4": 0,
            "5": 0,
        }

        for rating, count in rating_rows:
            rating_key = str(rating)
            if rating_key in rating_breakdown:
                rating_breakdown[rating_key] = count

        return {
            "success": True,
            "company_id": company_id,
            "company_name": company.name,
            "total_reviews": total_reviews,
            "average_rating": round(float(average_rating), 2),
            "rating_breakdown": rating_breakdown,
        }

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"ANALYTICS ERROR => {e}")
        logger.error(traceback.format_exc())

        raise HTTPException(status_code=500, detail=str(e))

# =========================================================
# DELETE REVIEW
# =========================================================

@router.delete("/delete/{review_id}")
async def delete_review(
    review_id: int,
    db: Session = Depends(get_db),
):
    try:
        review = db.query(Review).filter(Review.id == review_id).first()

        if not review:
            raise HTTPException(status_code=404, detail="Review not found")

        db.delete(review)
        db.commit()

        return {
            "success": True,
            "message": "Review deleted",
            "review_id": review_id,
        }

    except HTTPException:
        raise

    except Exception as e:
        db.rollback()
        logger.error(f"DELETE REVIEW ERROR => {e}")
        logger.error(traceback.format_exc())

        raise HTTPException(status_code=500, detail=str(e))
