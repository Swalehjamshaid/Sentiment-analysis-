# ==========================================================
# FILE: app/services/scraper.py
# TRUSTLYTICS AI SAAS - ENTERPRISE APIFY SCRAPER
# FULLY FIXED PRODUCTION VERSION
# ==========================================================

import asyncio
import hashlib
import logging
import traceback

from datetime import datetime
from typing import Dict, Any, List

from sqlalchemy import (
    select,
    func,
    desc
)

from sqlalchemy.ext.asyncio import AsyncSession

from apify_client import ApifyClient

from app.core.models import (
    Review,
    Company
)

# ==========================================================
# SAFE SETTINGS IMPORT
# ==========================================================

try:

    from app.core.config import settings

except Exception:

    class settings:

        APIFY_TOKEN = None

# ==========================================================
# LOGGER
# ==========================================================

logger = logging.getLogger(
    "app.services.scraper"
)

# ==========================================================
# REVIEW SERVICE
# ==========================================================

class ReviewService:

    # ======================================================
    # GET LATEST REVIEWS
    # ======================================================

    @staticmethod
    async def get_latest_reviews(

        db: AsyncSession,

        company_id: int,

        limit: int = 50
    ):

        try:

            stmt = (

                select(Review)

                .where(
                    Review.company_id == company_id
                )

                .order_by(
                    desc(Review.created_at)
                )

                .limit(limit)
            )

            result = await db.execute(
                stmt
            )

            return result.scalars().all()

        except Exception as e:

            logger.exception(
                f"❌ get_latest_reviews failed: {e}"
            )

            return []

    # ======================================================
    # GET TOTAL REVIEWS
    # ======================================================

    @staticmethod
    async def get_total_reviews(

        db: AsyncSession,

        company_id: int
    ):

        try:

            stmt = (

                select(
                    func.count(Review.id)
                )

                .where(
                    Review.company_id == company_id
                )
            )

            result = await db.execute(
                stmt
            )

            return result.scalar() or 0

        except Exception:

            return 0

    # ======================================================
    # GET AVERAGE RATING
    # ======================================================

    @staticmethod
    async def get_average_rating(

        db: AsyncSession,

        company_id: int
    ):

        try:

            stmt = (

                select(
                    func.avg(Review.rating)
                )

                .where(
                    Review.company_id == company_id
                )
            )

            result = await db.execute(
                stmt
            )

            avg = result.scalar()

            if avg is None:

                return 0

            return round(
                float(avg),
                2
            )

        except Exception:

            return 0

    # ======================================================
    # GET NEGATIVE REVIEWS
    # ======================================================

    @staticmethod
    async def get_negative_reviews(

        db: AsyncSession,

        company_id: int
    ):

        try:

            stmt = (

                select(Review)

                .where(
                    Review.company_id == company_id
                )

                .where(
                    Review.rating <= 2
                )
            )

            result = await db.execute(
                stmt
            )

            return result.scalars().all()

        except Exception:

            return []

    # ======================================================
    # GET DASHBOARD STATS
    # ======================================================

    @staticmethod
    async def get_dashboard_stats(

        db: AsyncSession,

        company_id: int
    ):

        total_reviews = await ReviewService.get_total_reviews(

            db=db,

            company_id=company_id
        )

        average_rating = await ReviewService.get_average_rating(

            db=db,

            company_id=company_id
        )

        negative_reviews = await ReviewService.get_negative_reviews(

            db=db,

            company_id=company_id
        )

        reputation_score = round(
            average_rating * 20,
            2
        )

        return {

            "total_reviews":
                total_reviews,

            "average_rating":
                average_rating,

            "negative_reviews":
                len(negative_reviews),

            "reputation_score":
                reputation_score
        }

# ==========================================================
# SAFE STRING
# ==========================================================

def safe_string(
    value,
    default=""
):

    try:

        if value is None:
            return default

        return str(value).strip()

    except Exception:

        return default

# ==========================================================
# SAFE INTEGER
# ==========================================================

def safe_int(
    value,
    default=0
):

    try:

        if value is None:
            return default

        return int(value)

    except Exception:

        return default

# ==========================================================
# SAFE FLOAT
# ==========================================================

def safe_float(
    value,
    default=0.0
):

    try:

        if value is None:
            return default

        return float(value)

    except Exception:

        return default

# ==========================================================
# SAFE DATETIME
# ==========================================================

def safe_datetime(value):

    try:

        if not value:

            return datetime.utcnow()

        if isinstance(value, datetime):

            return value.replace(
                tzinfo=None
            )

        value = str(value)

        value = value.replace(
            "Z",
            "+00:00"
        )

        parsed = datetime.fromisoformat(
            value
        )

        return parsed.replace(
            tzinfo=None
        )

    except Exception:

        return datetime.utcnow()

# ==========================================================
# CLEAN REVIEW TEXT
# ==========================================================

def clean_review_text(text):

    text = safe_string(
        text,
        ""
    )

    text = text.replace(
        "\n",
        " "
    )

    text = text.replace(
        "\r",
        " "
    )

    text = text.replace(
        "\t",
        " "
    )

    text = " ".join(
        text.split()
    )

    if len(text) > 5000:

        text = text[:5000]

    return text

# ==========================================================
# GENERATE HASH
# ==========================================================

def generate_hash(
    author,
    text
):

    raw = f"{author}_{text}"

    return hashlib.md5(

        raw.encode(
            "utf-8"
        )

    ).hexdigest()

# ==========================================================
# CREATE APIFY CLIENT
# ==========================================================

def create_apify_client():

    token = getattr(
        settings,
        "APIFY_TOKEN",
        None
    )

    if not token:

        logger.error(
            "❌ APIFY_TOKEN missing"
        )

        return None

    return ApifyClient(token)

# ==========================================================
# BUILD GOOGLE MAPS URL
# ==========================================================

def build_google_maps_url(
    place_id: str
):

    return (
        "https://www.google.com/maps/search/"
        f"?api=1&query_place_id={place_id}"
    )
# ==========================================================
# BUILD ACTOR INPUT
# ==========================================================

def build_actor_input(

    google_maps_url: str,

    target_limit: int

):

    return {

        "startUrls": [

            {
                "url":
                    google_maps_url
            }

        ],

        "language":
            "en",

        "maxReviews":
            target_limit,

        "reviewsSort":
            "newest",

        "reviewsOrigin":
            "all",

        "personalData":
            True,

        "maxImages":
            0,

        "maxCrawledPlaces":
            1,

        "proxy": {

            "useApifyProxy":
                True
        }
    }

# ==========================================================
# GET EXISTING REVIEWS
# ==========================================================

async def get_existing_reviews(

    session: AsyncSession,

    company_id: int
):

    stmt = (

        select(Review)

        .where(
            Review.company_id == company_id
        )
    )

    result = await session.execute(
        stmt
    )

    reviews = result.scalars().all()

    mapped = {}

    for review in reviews:

        mapped[
            review.google_review_id
        ] = review

    return mapped

# ==========================================================
# NORMALIZE REVIEW
# ==========================================================

def normalize_review(

    item: Dict[str, Any],

    company_id: int

):

    try:

        author_name = (

            item.get("name")

            or

            item.get("reviewerName")

            or

            item.get("authorName")

            or

            item.get("userName")

            or

            item.get("reviewer")

            or

            "Anonymous"
        )

        author_name = safe_string(
            author_name,
            "Anonymous"
        )

        review_text = (

            item.get("text")

            or

            item.get("reviewText")

            or

            item.get("review")

            or

            item.get("comment")

            or

            item.get("reviewDescription")

            or

            ""
        )

        review_text = clean_review_text(
            review_text
        )

        if not review_text.strip():

            logger.warning(
                f"⚠️ Empty review skipped: {item}"
            )

            return None

        rating = (

            item.get("stars")

            or

            item.get("rating")

            or

            item.get("score")

            or

            5
        )

        rating = safe_int(
            rating,
            5
        )

        rating = max(
            1,
            min(5, rating)
        )

        review_likes = (

            item.get("likesCount")

            or

            item.get("likes")

            or

            0
        )

        review_likes = safe_int(
            review_likes,
            0
        )

        review_time = (

            item.get("publishedAtDate")

            or

            item.get("publishedAt")

            or

            item.get("reviewDate")

            or

            item.get("date")
        )

        review_time = safe_datetime(
            review_time
        )

        google_review_id = (

            item.get("reviewId")

            or

            item.get("review_id")

            or

            item.get("id")
        )

        if not google_review_id:

            google_review_id = (

                f"{company_id}_"

                f"{generate_hash(author_name, review_text)}"
            )

        google_review_id = safe_string(
            google_review_id
        )

        sentiment_score = round(
            rating / 5,
            2
        )

        return {

            "google_review_id":
                google_review_id,

            "author_name":
                author_name,

            "rating":
                rating,

            "text":
                review_text,

            "google_review_time":
                review_time,

            "review_likes":
                review_likes,

            "sentiment_score":
                sentiment_score
        }

    except Exception as e:

        logger.exception(
            f"❌ Normalize failed: {e}"
        )

        return None

# ==========================================================
# MAIN SCRAPER
# ==========================================================

async def fetch_reviews_from_google(

    place_id: str,

    company_id: int,

    session: AsyncSession,

    target_limit: int = 100

) -> Dict[str, Any]:

    logger.info(
        f"🚀 SCRAPER STARTED | company_id={company_id}"
    )

    started_at = datetime.utcnow()

    try:

        if not place_id:

            logger.error(
                "❌ place_id missing"
            )

            return {

                "success": False,

                "inserted": 0,

                "updated": 0,

                "duplicates": 0,

                "fetched": 0,

                "reviews": []
            }

        existing_reviews = await get_existing_reviews(

            session=session,

            company_id=company_id
        )

        logger.info(
            f"📦 Existing reviews: {len(existing_reviews)}"
        )

        client = create_apify_client()

        if not client:

            return {

                "success": False,

                "inserted": 0,

                "updated": 0,

                "duplicates": 0,

                "fetched": 0,

                "reviews": []
            }

        google_maps_url = build_google_maps_url(
            place_id
        )

        existing_count = len(
            existing_reviews
        )

        logger.info(
            f"📦 Existing reviews in DB: {existing_count}"
        )

        dynamic_target_limit = (

            existing_count

            +

            target_limit
        )

        dynamic_target_limit = min(

            dynamic_target_limit,

            5000
        )

        logger.info(
            f"🚀 Dynamic APIFY fetch limit: {dynamic_target_limit}"
        )

        actor_input = build_actor_input(

            google_maps_url=
                google_maps_url,

            target_limit=
                dynamic_target_limit
        )

        logger.info(
            f"🚀 Requesting {dynamic_target_limit} reviews from APIFY"
        )

        logger.info(
            "🚀 Starting APIFY actor..."
        )

                     run = await asyncio.to_thread(
            client.actor(
                "compass~google-maps-reviews-scraper"
            ).call,
            run_input=actor_input
        )

        if not run:

            logger.error(
                "❌ Actor execution failed"
            )

            return {

                "success": False,

                "inserted": 0,

                "updated": 0,

                "duplicates": 0,

                "fetched": 0,

                "reviews": []
            }

        dataset_id = run.get(
            "defaultDatasetId"
        )

        if not dataset_id:

            logger.error(
                "❌ Dataset ID missing"
            )

            return {

                "success": False,

                "inserted": 0,

                "updated": 0,

                "duplicates": 0,

                "fetched": 0,

                "reviews": []
            }

        dataset = client.dataset(
            dataset_id
        )

        raw_reviews = []

        # ==================================================
        # WAIT FOR DATASET READINESS
        # ==================================================

        for attempt in range(10):

            try:

                                           dataset_items = await asyncio.to_thread(
                    dataset.list_items,
                    clean=True,
                    limit=dynamic_target_limit
                )

                raw_reviews = dataset_items.items

                logger.info(
                    f"📦 RAW REVIEWS RECEIVED: {len(raw_reviews)}"
                )
                if raw_reviews:

                    logger.info(
                        f"✅ Dataset ready | reviews={len(raw_reviews)}"
                    )

                    break

            except Exception as dataset_error:

                logger.warning(
                    f"⚠️ Dataset retry {attempt + 1}: {dataset_error}"
                )

            await asyncio.sleep(2)

        if not raw_reviews:

            logger.warning(
                "⚠️ No reviews returned from APIFY"
            )

        inserted_reviews = []

        inserted_count = 0
        updated_count = 0
        duplicate_count = 0

        memory_hashes = set()

        # ==================================================
        # PROCESS REVIEWS
        # ==================================================

        for item in raw_reviews:

            try:

                normalized = normalize_review(

                    item=item,

                    company_id=company_id
                )

                if not normalized:

                    continue

                google_review_id = normalized.get(
                    "google_review_id"
                )

                memory_key = normalized[
                    "google_review_id"
                ]

                logger.info(
                    f"PROCESSING REVIEW: {memory_key}"
                )

                # ==========================================
                # MEMORY DUPLICATE CHECK
                # ==========================================

                if memory_key in memory_hashes:

                    duplicate_count += 1

                    continue

                memory_hashes.add(
                    memory_key
                )

                # ==========================================
                # DATABASE DUPLICATE CHECK
                # ==========================================

                existing_review = existing_reviews.get(
                    google_review_id
                )

                # ==========================================
                # UPDATE EXISTING REVIEW
                # ==========================================

                if existing_review:

                    updated = False

                    if existing_review.text != normalized["text"]:

                        existing_review.text = normalized["text"]

                        updated = True

                    if existing_review.rating != normalized["rating"]:

                        existing_review.rating = normalized["rating"]

                        updated = True

                    if existing_review.review_likes != normalized["review_likes"]:

                        existing_review.review_likes = normalized["review_likes"]

                        updated = True

                    if updated:

                        existing_review.sentiment_score = normalized["sentiment_score"]

                        existing_review.google_review_time = normalized["google_review_time"]

                        updated_count += 1

                    else:

                        duplicate_count += 1

                    continue

                # ==========================================
                # INSERT NEW REVIEW
                # ==========================================

                logger.info(
                    f"➕ INSERTING REVIEW: {normalized['google_review_id']}"
                )

                new_review = Review(

                    company_id=
                        company_id,

                    google_review_id=
                        normalized["google_review_id"],

                    author_name=
                        normalized["author_name"],

                    rating=
                        normalized["rating"],

                    sentiment_score=
                        normalized["sentiment_score"],

                    text=
                        normalized["text"],

                    google_review_time=
                        normalized["google_review_time"],

                    review_likes=
                        normalized["review_likes"],

                    first_seen_at=
                        datetime.utcnow(),

                    created_at=
                        datetime.utcnow()
                )

                session.add(
                    new_review
                )

                inserted_reviews.append(
                    normalized
                )

                inserted_count += 1

                # ======================================
                # HARD INSERT LIMIT
                # ======================================

                if inserted_count >= target_limit:

                    logger.info(
                        f"🛑 Target insert limit reached: {target_limit}"
                    )

                    break

            except Exception as row_error:

                logger.exception(
                    f"❌ Row processing failed: {row_error}"
                )

                continue

        # ==================================================
        # COMMIT
        # ==================================================

        try:

            logger.info(
                f"🚀 Committing {inserted_count} reviews to database"
            )

            await session.commit()

            logger.info(
                "✅ Database commit successful"
            )

        except Exception as commit_error:

            await session.rollback()

            logger.exception(
                f"❌ Commit failed: {commit_error}"
            )

            return {

                "success": False,

                "inserted": 0,

                "updated": 0,

                "duplicates": 0,

                "fetched": len(raw_reviews),

                "reviews": []
            }

        # ==================================================
        # MINIMUM EXECUTION TIME UX
        # ==================================================

        execution_seconds = (

            datetime.utcnow() - started_at

        ).total_seconds()

        if execution_seconds < 5:

            await asyncio.sleep(
                5 - execution_seconds
            )

        # ==================================================
        # FINAL LOGS
        # ==================================================

        logger.info(
            f"✅ FETCHED: {len(raw_reviews)}"
        )

        logger.info(
            f"✅ INSERTED: {inserted_count}"
        )

        logger.info(
            f"✅ UPDATED: {updated_count}"
        )

        logger.info(
            f"✅ DUPLICATES: {duplicate_count}"
        )

        # ==================================================
        # RESPONSE
        # ==================================================

        return {

            "success": True,

            "message":
                f"{inserted_count} new reviews added successfully",

            "inserted":
                inserted_count,

            "updated":
                updated_count,

            "duplicates":
                duplicate_count,

            "fetched":
                len(raw_reviews),

            "requested":
                dynamic_target_limit,

            "existing":
                existing_count,

            "final_total":
                existing_count + inserted_count,

            "reviews":
                inserted_reviews
        }

    except Exception as e:

        try:

            await session.rollback()

        except Exception:

            pass

        logger.exception(
            f"❌ SCRAPER FAILED: {e}"
        )

        logger.error(
            traceback.format_exc()
        )

        return {

            "success": False,

            "inserted": 0,

            "updated": 0,

            "duplicates": 0,

            "fetched": 0,

            "reviews": [],

            "error": str(e)
        }
