# =========================================================
# FILE: review_saas/app/routes/reviews.py
# TRUSTLYTICS AI - ENTERPRISE REVIEWS ROUTER
# FULLY STABILIZED VERSION
# =========================================================

print("🔥 REVIEWS.PY IMPORT STARTED")

# =========================================================
# SAFE IMPORTS
# =========================================================

try:

    from fastapi import (
        APIRouter,
        Depends,
        HTTPException,
        Query
    )

    print("✅ FASTAPI IMPORTED")

except Exception as e:

    print(f"❌ FASTAPI IMPORT FAILED => {e}")

try:

    from sqlalchemy.orm import Session

    from sqlalchemy import (
        desc,
        func,
        and_
    )

    print("✅ SQLALCHEMY IMPORTED")

except Exception as e:

    print(f"❌ SQLALCHEMY IMPORT FAILED => {e}")

try:

    from typing import Optional

    from datetime import datetime

    import traceback

    import logging

    print("✅ PYTHON MODULES IMPORTED")

except Exception as e:

    print(f"❌ PYTHON MODULE IMPORT FAILED => {e}")

# =========================================================
# DATABASE IMPORT
# =========================================================

try:

    from app.core.db import get_db

    print("✅ DATABASE IMPORTED")

except Exception as e:

    print(f"❌ DATABASE IMPORT FAILED => {e}")

    get_db = None

# =========================================================
# MODELS IMPORT
# =========================================================

try:

   from app.core.models import (
    Company,
    Review
)

    print("✅ MODELS IMPORTED")

except Exception as e:

    print(f"❌ MODELS IMPORT FAILED => {e}")

    Company = None
    Review = None

# =========================================================
# SCRAPER IMPORT
# =========================================================

SCRAPER_AVAILABLE = False

try:

    from app.scraper import scrape_google_reviews

    SCRAPER_AVAILABLE = True

    print("✅ SCRAPER IMPORTED")

except Exception as e:

    scrape_google_reviews = None

    print(f"❌ SCRAPER IMPORT FAILED => {e}")

# =========================================================
# LOGGER
# =========================================================

logger = logging.getLogger(__name__)

logger.setLevel(logging.INFO)

print("✅ LOGGER READY")

# =========================================================
# ROUTER
# =========================================================

router = APIRouter(

    prefix="/api/reviews",

    tags=["Reviews"]
)

print("✅ REVIEWS ROUTER CREATED")

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

    rating: Optional[int] = None,

    sentiment: Optional[str] = None,

    db: Session = Depends(get_db)
):

    try:

        logger.info(
            f"📊 FETCHING REVIEWS => {company_id}"
        )

        if Company is None:

            raise HTTPException(

                status_code=500,

                detail="Company model import failed"
            )

        if Review is None:

            raise HTTPException(

                status_code=500,

                detail="Review model import failed"
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

        # =================================================
        # FILTERS
        # =================================================

        if rating is not None:

            query = query.filter(
                Review.rating == rating
            )

        if sentiment:

            query = query.filter(
                func.lower(
                    Review.sentiment
                ) == sentiment.lower()
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

                "content": review.review_text,

                "review_text": review.review_text,

                "sentiment": review.sentiment,

                "source": review.source,

                "review_date": review.review_date,

                "created_at": review.created_at
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

    db: Session = Depends(get_db)
):

    try:

        logger.info(
            f"🚀 SYNC STARTED => {company_id}"
        )

        if Company is None:

            raise HTTPException(

                status_code=500,

                detail="Company model import failed"
            )

        if Review is None:

            raise HTTPException(

                status_code=500,

                detail="Review model import failed"
            )

        company = db.query(Company).filter(
            Company.id == company_id
        ).first()

        if not company:

            raise HTTPException(

                status_code=404,

                detail="Company not found"
            )

        # =================================================
        # SCRAPER CHECK
        # =================================================

        if not SCRAPER_AVAILABLE:

            return {

                "success": False,

                "message":
                    "scraper.py import failed",

                "company_id": company_id
            }

        # =================================================
        # PLACE ID
        # =================================================

        google_place_id = getattr(
            company,
            "google_place_id",
            None
        )

        if not google_place_id:

            google_place_id = getattr(
                company,
                "place_id",
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
            f"🌍 SCRAPING GOOGLE REVIEWS => {google_place_id}"
        )

        # =================================================
        # SCRAPE REVIEWS
        # =================================================

        scraped_reviews = scrape_google_reviews(
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

        # =================================================
        # INSERT REVIEWS
        # =================================================

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

                    continue

                author = item.get(
                    "author",
                    "Anonymous"
                )

                rating = int(
                    item.get(
                        "rating",
                        0
                    )
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

                # =========================================
                # SENTIMENT
                # =========================================

                sentiment = "neutral"

                if rating >= 4:

                    sentiment = "positive"

                elif rating <= 2:

                    sentiment = "negative"

                # =========================================
                # CREATE REVIEW
                # =========================================

                review = Review(

                    company_id=company_id,

                    author=author,

                    rating=rating,

                    review_text=review_text,

                    sentiment=sentiment,

                    source=item.get(
                        "source",
                        "Google"
                    ),

                    review_date=datetime.utcnow(),

                    created_at=datetime.utcnow()
                )

                db.add(review)

                inserted_reviews += 1

            except Exception as review_error:

                failed_reviews += 1

                logger.error(
                    f"❌ REVIEW INSERT ERROR => {review_error}"
                )

        # =================================================
        # DATABASE COMMIT
        # =================================================

        db.commit()

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

        db.rollback()

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

    db: Session = Depends(get_db)
):

    try:

        reviews = db.query(Review).filter(
            Review.company_id == company_id
        ).all()

        total_reviews = len(reviews)

        if total_reviews == 0:

            return {

                "success": True,

                "company_id": company_id,

                "total_reviews": 0,

                "average_rating": 0,

                "positive_reviews": 0,

                "negative_reviews": 0,

                "neutral_reviews": 0
            }

        average_rating = round(

            sum([
                review.rating
                for review in reviews
            ]) / total_reviews,

            2
        )

        positive_reviews = len([

            review for review in reviews

            if review.sentiment == "positive"
        ])

        negative_reviews = len([

            review for review in reviews

            if review.sentiment == "negative"
        ])

        neutral_reviews = len([

            review for review in reviews

            if review.sentiment == "neutral"
        ])

        return {

            "success": True,

            "company_id": company_id,

            "total_reviews": total_reviews,

            "average_rating": average_rating,

            "positive_reviews": positive_reviews,

            "negative_reviews": negative_reviews,

            "neutral_reviews": neutral_reviews
        }

    except Exception as e:

        logger.error(
            f"❌ ANALYTICS ERROR => {e}"
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

    db: Session = Depends(get_db)
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

            "message": "Review deleted",

            "review_id": review_id
        }

    except HTTPException:
        raise

    except Exception as e:

        db.rollback()

        raise HTTPException(

            status_code=500,

            detail=str(e)
        )

# =========================================================
# ROUTER LOADED
# =========================================================

print("✅ REVIEWS ROUTER FULLY LOADED")
