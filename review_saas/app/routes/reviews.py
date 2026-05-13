# filename: app/routes/reviews.py

# ==========================================================
# REVIEW ROUTES — FULLY INTEGRATED WITH POSTGRESQL
# ==========================================================

import logging

from datetime import datetime

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
)

from sqlalchemy import (
    select,
    func,
)

from sqlalchemy.ext.asyncio import AsyncSession

# ==========================================================
# INTERNAL IMPORTS
# ==========================================================

from app.core.db import get_db

from app.core.models import (
    Review,
    Company,
)

from app.services.scraper import (
    fetch_reviews_from_google,
    ReviewService
)

# ==========================================================
# ROUTER
# ==========================================================

router = APIRouter()

logger = logging.getLogger(
    "app.routes.reviews"
)

# ==========================================================
# INGEST REVIEWS FROM GOOGLE
# ==========================================================

@router.post("/reviews/ingest/{company_id}")

async def ingest_reviews(

    company_id: int,

    db: AsyncSession = Depends(get_db)

):

    logger.info(
        f"🚀 Sync requested for company_id: {company_id}"
    )

    try:

        # ==================================================
        # VERIFY COMPANY
        # ==================================================

        company_stmt = select(
            Company
        ).where(
            Company.id == company_id
        )

        company_result = await db.execute(
            company_stmt
        )

        company = company_result.scalars().first()

        if not company:

            raise HTTPException(

                status_code=404,

                detail="Company not found"
            )

        if not company.google_place_id:

            raise HTTPException(

                status_code=400,

                detail="Google Place ID missing"
            )

        # ==================================================
        # FETCH REVIEWS
        # ==================================================

        scraped_reviews = await fetch_reviews_from_google(

            place_id=
                company.google_place_id,

            company_id=
                company_id,

            session=
                db,

            target_limit=
                100
        )

        if not scraped_reviews:

            logger.warning(
                "⚠️ No reviews fetched from scraper"
            )

            return {

                "status":
                    "success",

                "reviews_collected":
                    0,

                "message":
                    "No new reviews found"
            }

        # ==================================================
        # SAVE REVIEWS
        # ==================================================

        inserted_count = 0

        for r_data in scraped_reviews:

            try:

                google_review_id = r_data.get(
                    "google_review_id"
                )

                if not google_review_id:
                    continue

                # ==========================================
                # DUPLICATE CHECK
                # ==========================================

                duplicate_stmt = select(
                    Review
                ).where(
                    Review.google_review_id
                    ==
                    google_review_id
                )

                duplicate_result = await db.execute(
                    duplicate_stmt
                )

                existing_review = (
                    duplicate_result
                    .scalars()
                    .first()
                )

                if existing_review:
                    continue

                # ==========================================
                # SAFE VALUES
                # ==========================================

                author_name = (
                    r_data.get(
                        "author_name"
                    )
                    or "Anonymous"
                )

                rating = (
                    r_data.get(
                        "rating"
                    )
                    or 5
                )

                text = (
                    r_data.get(
                        "text"
                    )
                    or "No content provided."
                )

                likes = (
                    r_data.get(
                        "review_likes"
                    )
                    or 0
                )

                review_time = (
                    r_data.get(
                        "google_review_time"
                    )
                    or datetime.utcnow()
                )

                # ==========================================
                # REMOVE TZINFO
                # ==========================================

                if (
                    hasattr(review_time, "tzinfo")
                    and review_time.tzinfo
                ):

                    review_time = (
                        review_time
                        .replace(tzinfo=None)
                    )

                # ==========================================
                # INSERT REVIEW
                # ==========================================

                new_review = Review(

                    company_id=
                        company_id,

                    google_review_id=
                        google_review_id,

                    author_name=
                        author_name,

                    rating=
                        rating,

                    sentiment_score=
                        round(
                            rating / 5,
                            2
                        ),

                    text=
                        text,

                    google_review_time=
                        review_time,

                    first_seen_at=
                        datetime.utcnow(),

                    review_likes=
                        likes
                )

                db.add(new_review)

                inserted_count += 1

            except Exception as row_error:

                logger.exception(
                    f"❌ Failed processing review: {row_error}"
                )

                continue

        # ==================================================
        # COMMIT
        # ==================================================

        await db.commit()

        logger.info(
            f"✅ Sync complete | Added: {inserted_count}"
        )

        return {

            "status":
                "success",

            "reviews_collected":
                inserted_count,

            "company":
                company.name
        }

    except HTTPException:

        raise

    except Exception as e:

        await db.rollback()

        logger.exception(
            "❌ Review sync failed"
        )

        raise HTTPException(

            status_code=500,

            detail=str(e)
        )

# ==========================================================
# GET COMPANY REVIEWS
# ==========================================================

@router.get("/reviews/company/{company_id}")

async def get_company_reviews(

    company_id: int,

    limit: int = 100,

    db: AsyncSession = Depends(get_db)

):

    try:

        stmt = (

            select(Review)

            .where(
                Review.company_id == company_id
            )

            .order_by(
                Review.google_review_time.desc()
            )

            .limit(limit)
        )

        result = await db.execute(stmt)

        reviews = result.scalars().all()

        items = []

        for r in reviews:

            items.append({

                "id":
                    r.id,

                "author":
                    r.author_name,

                "author_name":
                    r.author_name,

                "rating":
                    r.rating,

                "review_text":
                    r.text,

                "text":
                    r.text,

                "created_at":
                    (
                        r.google_review_time.isoformat()
                        if r.google_review_time
                        else None
                    ),

                "review_likes":
                    r.review_likes,

                "sentiment":
                    (
                        "positive"
                        if (r.rating or 0) >= 4

                        else "negative"

                        if (r.rating or 0) <= 2

                        else "neutral"
                    )
            })

        return {

            "status":
                "success",

            "total_reviews":
                len(items),

            "reviews":
                items
        }

    except Exception as e:

        logger.exception(
            "❌ Failed loading company reviews"
        )

        raise HTTPException(

            status_code=500,

            detail=str(e)
        )

# ==========================================================
# AI INSIGHTS
# ==========================================================

@router.get("/dashboard/ai/insights")

async def ai_insights(

    company_id: int,

    db: AsyncSession = Depends(get_db)

):

    try:

        stmt = select(
            Review
        ).where(
            Review.company_id == company_id
        )

        result = await db.execute(stmt)

        reviews = result.scalars().all()

        total_reviews = len(reviews)

        if total_reviews == 0:

            return {

                "status":
                    "success",

                "kpis": {

                    "average_rating": 0,

                    "reputation_score": 0
                },

                "metadata": {

                    "total_reviews": 0
                }
            }

        ratings = [

            r.rating
            for r in reviews
            if r.rating
        ]

        avg_rating = round(
            sum(ratings) / len(ratings),
            2
        )

        reputation_score = round(
            avg_rating * 20,
            2
        )

        rating_distribution = {

            "1": 0,
            "2": 0,
            "3": 0,
            "4": 0,
            "5": 0
        }

        for r in reviews:

            if r.rating:

                key = str(r.rating)

                if key in rating_distribution:

                    rating_distribution[key] += 1

        return {

            "status":
                "success",

            "metadata": {

                "total_reviews":
                    total_reviews
            },

            "kpis": {

                "average_rating":
                    avg_rating,

                "reputation_score":
                    reputation_score
            },

            "visualizations": {

                "ratings":
                    rating_distribution,

                "sentiment": {

                    "positive":
                        len(
                            [r for r in reviews if (r.rating or 0) >= 4]
                        ),

                    "neutral":
                        len(
                            [r for r in reviews if (r.rating or 0) == 3]
                        ),

                    "negative":
                        len(
                            [r for r in reviews if (r.rating or 0) <= 2]
                        )
                }
            }
        }

    except Exception as e:

        logger.exception(
            "❌ AI insights failed"
        )

        raise HTTPException(

            status_code=500,

            detail=str(e)
        )

# ==========================================================
# REVENUE RISK
# ==========================================================

@router.get("/dashboard/revenue/{company_id}")

async def revenue_risk(

    company_id: int,

    db: AsyncSession = Depends(get_db)

):

    try:

        stmt = select(
            func.avg(Review.rating)
        ).where(
            Review.company_id == company_id
        )

        result = await db.execute(stmt)

        avg_rating = result.scalar() or 0

        risk_percent = max(
            0,
            round((5 - avg_rating) * 20, 2)
        )

        return {

            "status":
                "success",

            "average_rating":
                round(avg_rating, 2),

            "risk_percent":
                risk_percent
        }

    except Exception as e:

        logger.exception(
            "❌ Revenue analytics failed"
        )

        raise HTTPException(

            status_code=500,

            detail=str(e)
        )

# ==========================================================
# HEALTH TEST
# ==========================================================

@router.get("/reviews/health")

async def review_health():

    return {

        "status":
            "healthy",

        "service":
            "reviews-api"
    }`
