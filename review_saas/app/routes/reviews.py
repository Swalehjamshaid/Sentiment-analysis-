# filename: app/routes/reviews.py

import logging

from datetime import datetime, timezone

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

from app.core.db import get_session

from app.core.models import (
    Review,
    Company,
)

from app.services.scraper import (
    fetch_reviews_from_google
)

# ==========================================================
# ROUTER
# ==========================================================

router = APIRouter()

logger = logging.getLogger(
    "app.routes.reviews"
)

# ==========================================================
# INGEST REVIEWS
# ==========================================================

@router.post("/reviews/ingest/{company_id}")

async def ingest_reviews(

    company_id: int,

    db: AsyncSession = Depends(get_session)

):

    """
    Triggered by Sync Live Data button.
    Fetches reviews and stores them safely.
    """

    logger.info(
        f"🚀 Sync requested for company_id: {company_id}"
    )

    try:

        # ==================================================
        # VERIFY COMPANY
        # ==================================================

        res = await db.execute(

            select(Company).where(
                Company.id == company_id
            )
        )

        company = res.scalar_one_or_none()

        if not company:

            logger.error(
                f"❌ Company {company_id} not found"
            )

            raise HTTPException(

                status_code=404,

                detail="Company not found"
            )

        if not company.google_place_id:

            logger.error(
                f"❌ Missing Google Place ID for company {company_id}"
            )

            raise HTTPException(

                status_code=400,

                detail="Missing Google Place ID"
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
                db
        )

        if not scraped_reviews:

            logger.info(
                f"ℹ️ No new reviews found for company {company_id}"
            )

            return {

                "status": "success",

                "reviews_collected": 0
            }

        # ==================================================
        # PREPARE INSERT
        # ==================================================

        new_entries = 0

        allowed_cols = (
            Review.__table__.columns.keys()
        )

        for r_data in scraped_reviews:

            try:

                # ==========================================
                # FIX DATETIME ISSUES
                # ==========================================

                if "google_review_time" in r_data:

                    review_time = r_data.pop(
                        "google_review_time"
                    )

                    if review_time:

                        # Remove timezone info
                        if (
                            hasattr(review_time, "tzinfo")
                            and review_time.tzinfo
                        ):

                            review_time = (
                                review_time
                                .replace(tzinfo=None)
                            )

                    r_data["first_seen_at"] = (
                        review_time
                    )

                # ==========================================
                # DEFAULT VALUES
                # ==========================================

                if not r_data.get("author_name"):

                    r_data["author_name"] = (
                        "Anonymous"
                    )

                if not r_data.get("rating"):

                    r_data["rating"] = 5

                if not r_data.get("text"):

                    r_data["text"] = (
                        "No content provided."
                    )

                if not r_data.get("review_likes"):

                    r_data["review_likes"] = 0

                # ==========================================
                # FILTER ALLOWED COLS
                # ==========================================

                filtered_data = {

                    k: v

                    for k, v in r_data.items()

                    if k in allowed_cols
                }

                # ==========================================
                # DUPLICATE CHECK
                # ==========================================

                stmt = select(Review).where(

                    Review.company_id ==
                    company_id,

                    Review.google_review_id ==
                    filtered_data.get(
                        "google_review_id"
                    )
                )

                existing = await db.execute(stmt)

                exists = (
                    existing.scalar_one_or_none()
                )

                if exists:

                    continue

                # ==========================================
                # INSERT REVIEW
                # ==========================================

                new_review = Review(

                    company_id=
                        company_id,

                    **filtered_data
                )

                db.add(new_review)

                new_entries += 1

            except Exception as row_error:

                logger.exception(
                    f"❌ Failed processing review row: {row_error}"
                )

                continue

        # ==================================================
        # COMMIT
        # ==================================================

        if new_entries > 0:

            await db.commit()

            logger.info(

                f"✅ Sync complete for ID {company_id} | Added: {new_entries}"
            )

        else:

            logger.info(

                f"ℹ️ All fetched reviews already existed for company {company_id}"
            )

        return {

            "status": "success",

            "reviews_collected": new_entries
        }

    except HTTPException:

        raise

    except Exception as e:

        await db.rollback()

        logger.exception(
            f"❌ Sync failed for ID {company_id}"
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

    start: str = "",

    end: str = "",

    db: AsyncSession = Depends(get_session)

):

    """
    Dashboard AI insights endpoint.
    """

    try:

        # ==================================================
        # BASE QUERY
        # ==================================================

        query = select(Review).where(
            Review.company_id == company_id
        )

        # ==================================================
        # OPTIONAL DATE FILTER
        # ==================================================

        if start:

            try:

                start_dt = datetime.fromisoformat(
                    start
                )

                query = query.where(
                    Review.first_seen_at >= start_dt
                )

            except Exception:

                pass

        if end:

            try:

                end_dt = datetime.fromisoformat(
                    end
                )

                query = query.where(
                    Review.first_seen_at <= end_dt
                )

            except Exception:

                pass

        # ==================================================
        # EXECUTE
        # ==================================================

        result = await db.execute(query)

        reviews = result.scalars().all()

        total = len(reviews)

        avg_score = (

            sum(
                r.rating
                for r in reviews
                if r.rating
            ) / total

            if total > 0 else 0
        )

        # ==================================================
        # SIMPLE VISUAL DATA
        # ==================================================

        rating_counts = {
            "1": 0,
            "2": 0,
            "3": 0,
            "4": 0,
            "5": 0,
        }

        for r in reviews:

            if r.rating:

                key = str(r.rating)

                if key in rating_counts:

                    rating_counts[key] += 1

        # ==================================================
        # RESPONSE
        # ==================================================

        return {

            "status": "success",

            "metadata": {

                "total_reviews": total
            },

            "kpis": {

                "average_rating":
                    round(avg_score, 2),

                "reputation_score":
                    round(avg_score * 20, 2)
            },

            "visualizations": {

                "ratings":
                    rating_counts,

                "emotions": {

                    "Joy": 75,

                    "Trust": 64,

                    "Fear": 12,

                    "Anger": 18,

                    "Sadness": 22
                },

                "sentiment_trend": [

                    {
                        "month": "Jan",
                        "avg": 72
                    },

                    {
                        "month": "Feb",
                        "avg": 76
                    },

                    {
                        "month": "Mar",
                        "avg": 82
                    },

                    {
                        "month": "Apr",
                        "avg": 86
                    }
                ]
            }
        }

    except Exception as e:

        logger.exception(
            "❌ AI insight generation failed"
        )

        raise HTTPException(

            status_code=500,

            detail="Internal Server Error"
        )

# ==========================================================
# LATEST REVIEWS
# ==========================================================

@router.get("/dashboard/latest-reviews")

async def latest_reviews(

    company_id: int,

    limit: int = 100,

    db: AsyncSession = Depends(get_session)

):

    try:

        stmt = (

            select(Review)

            .where(
                Review.company_id == company_id
            )

            .order_by(
                Review.first_seen_at.desc()
            )

            .limit(limit)
        )

        result = await db.execute(stmt)

        reviews = result.scalars().all()

        items = []

        for r in reviews:

            items.append({

                "id": r.id,

                "author_name":
                    r.author_name,

                "rating":
                    r.rating,

                "review_text":
                    r.text,

                "review_date":
                    (
                        r.first_seen_at.isoformat()
                        if r.first_seen_at
                        else None
                    ),

                "sentiment":
                    (
                        "positive"
                        if (r.rating or 0) >= 4
                        else "negative"
                        if (r.rating or 0) <= 2
                        else "neutral"
                    )
            })

        return items

    except Exception as e:

        logger.exception(
            "❌ Latest reviews endpoint failed"
        )

        raise HTTPException(

            status_code=500,

            detail="Internal Server Error"
        )

# ==========================================================
# REVENUE
# ==========================================================

@router.get("/dashboard/revenue")

async def revenue_metrics(

    company_id: int,

    db: AsyncSession = Depends(get_session)

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

            "risk_percent":
                risk_percent,

            "impact":
                f"{risk_percent}%"
        }

    except Exception as e:

        logger.exception(
            "❌ Revenue endpoint failed"
        )

        raise HTTPException(

            status_code=500,

            detail="Internal Server Error"
        )
