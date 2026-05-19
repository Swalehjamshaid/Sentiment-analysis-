# ==========================================================
# FILE: app/services/scraper.py
# FINAL ENTERPRISE APIFY SCRAPER
# ==========================================================
# 
# FULLY INTEGRATED WITH:
#
# ✅ FastAPI
# ✅ PostgreSQL
# ✅ Dashboard Analytics
# ✅ AI Chatbot
# ✅ APIFY
# ✅ Railway
# ✅ Async SQLAlchemy
# ✅ Duplicate Detection
# ✅ Existing Review Comparison
# ✅ Dashboard Population
# ✅ Review Persistence
# ✅ Production Logging
#
# ==========================================================

import asyncio
import hashlib
import logging
import traceback

from datetime import datetime
from typing import List, Dict, Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apify_client import ApifyClient

from app.core.models import Review

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
    pass

# ==========================================================
# SAFE HELPERS
# ==========================================================

def safe_string(
    value,
    default=""
):

    try:

        if value is None:
            return default

        value = str(value)

        value = value.strip()

        return value

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
        "No review text"
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
# APIFY TOKEN
# ==========================================================

def get_apify_token():

    from app.core.config import settings

    token = getattr(
        settings,
        "APIFY_TOKEN",
        None
    )

    if not token:

        raise ValueError(
            "❌ APIFY_TOKEN missing"
        )

    return token

# ==========================================================
# CREATE APIFY CLIENT
# ==========================================================

def create_apify_client():

    token = get_apify_token()

    return ApifyClient(token)

# ==========================================================
# APIFY ACTOR INPUT
# ==========================================================

def build_actor_input(
    place_id: str,
    target_limit: int
):

    return {

        "startUrls": [

            {
                "url":
                    f"https://www.google.com/maps/place/?q=place_id:{place_id}"
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
                True,

            "apifyProxyGroups": [

                "RESIDENTIAL"
            ]
        }
    }

# ==========================================================
# GET EXISTING REVIEW IDS
# ==========================================================

async def get_existing_review_ids(

    db: AsyncSession,
    company_id: int

):

    stmt = select(
        Review.google_review_id
    ).where(
        Review.company_id == company_id
    )

    result = await db.execute(stmt)

    rows = result.scalars().all()

    return set(rows)

# ==========================================================
# NORMALIZE REVIEW
# ==========================================================

def normalize_review(
    item,
    company_id
):

    try:

        # ==================================================
        # AUTHOR
        # ==================================================

        author_name = safe_string(

            item.get("name")

            or item.get("reviewerName")

            or item.get("authorName")

            or "Anonymous"
        )

        # ==================================================
        # REVIEW TEXT
        # ==================================================

        review_text = clean_review_text(

            item.get("text")

            or item.get("reviewText")

            or item.get("review")

            or "No review text"
        )

        # ==================================================
        # RATING
        # ==================================================

        rating = safe_int(

            item.get("stars")

            or item.get("rating")

            or 5
        )

        if rating < 1:
            rating = 1

        if rating > 5:
            rating = 5

        # ==================================================
        # LIKES
        # ==================================================

        likes = safe_int(

            item.get("likesCount")

            or item.get("likes")

            or 0
        )

        # ==================================================
        # DATE
        # ==================================================

        review_time = safe_datetime(

            item.get("publishedAtDate")

            or item.get("publishedAt")

            or item.get("date")
        )

        # ==================================================
        # GOOGLE REVIEW ID
        # ==================================================

        google_review_id = (

            item.get("reviewId")

            or item.get("review_id")
        )

        if not google_review_id:

            google_review_id = (

                f"{company_id}_"

                f"{generate_hash(author_name, review_text)}"
            )

        # ==================================================
        # SENTIMENT
        # ==================================================

        sentiment_score = round(
            rating / 5,
            2
        )

        # ==================================================
        # RETURN
        # ==================================================

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
                likes,

            "sentiment_score":
                sentiment_score
        }

    except Exception as e:

        logger.exception(
            f"❌ Normalize review failed: {e}"
        )

        return None

# ==========================================================
# MAIN SCRAPER FUNCTION
# ==========================================================

async def fetch_reviews_from_google(

    place_id: str,

    company_id: int,

    session: AsyncSession,

    target_limit: int = 100

) -> List[Dict[str, Any]]:

    logger.info(
        f"🚀 ENTERPRISE APIFY SCRAPER STARTED | company={company_id}"
    )

    try:

        # ==================================================
        # VALIDATION
        # ==================================================

        if not place_id:

            logger.error(
                "❌ place_id missing"
            )

            return []

        # ==================================================
        # EXISTING REVIEWS
        # ==================================================

        existing_ids = await get_existing_review_ids(

            session,
            company_id
        )

        logger.info(
            f"📦 Existing reviews in DB: {len(existing_ids)}"
        )

        # ==================================================
        # CREATE CLIENT
        # ==================================================

        client = create_apify_client()

        # ==================================================
        # BUILD INPUT
        # ==================================================

        actor_input = build_actor_input(

            place_id=
                place_id,

            target_limit=
                target_limit
        )

        logger.info(
            "🚀 Launching APIFY actor..."
        )

        # ==================================================
        # RUN APIFY ACTOR
        # ==================================================

        run = await asyncio.to_thread(

            client.actor(
                "compass/google-maps-reviews-scraper"
            ).call,

            run_input=actor_input
        )

        if not run:

            logger.error(
                "❌ APIFY actor failed"
            )

            return []

        # ==================================================
        # DATASET
        # ==================================================

        dataset_id = run.get(
            "defaultDatasetId"
        )

        if not dataset_id:

            logger.error(
                "❌ Dataset ID missing"
            )

            return []

        logger.info(
            f"📦 Dataset ID: {dataset_id}"
        )

        dataset = client.dataset(
            dataset_id
        )

        dataset_items = await asyncio.to_thread(
            dataset.list_items
        )

        raw_reviews = dataset_items.items

        logger.info(
            f"📦 APIFY returned {len(raw_reviews)} reviews"
        )

        if not raw_reviews:

            logger.warning(
                "⚠️ No reviews returned"
            )

            return []

        # ==================================================
        # PROCESS REVIEWS
        # ==================================================

        inserted_reviews = []

        memory_hashes = set()

        for item in raw_reviews:

            try:

                normalized = normalize_review(

                    item,
                    company_id
                )

                if not normalized:
                    continue

                google_review_id = normalized.get(
                    "google_review_id"
                )

                if not google_review_id:
                    continue

                # ==========================================
                # EXISTING DATABASE CHECK
                # ==========================================

                if google_review_id in existing_ids:
                    continue

                # ==========================================
                # MEMORY DUPLICATE CHECK
                # ==========================================

                duplicate_key = generate_hash(

                    normalized["author_name"],
                    normalized["text"]
                )

                if duplicate_key in memory_hashes:
                    continue

                memory_hashes.add(
                    duplicate_key
                )

                # ==========================================
                # INSERT INTO DATABASE
                # ==========================================

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

                    first_seen_at=
                        datetime.utcnow(),

                    review_likes=
                        normalized["review_likes"],

                    created_at=
                        datetime.utcnow()
                )

                session.add(
                    new_review
                )

                inserted_reviews.append(
                    normalized
                )

            except Exception as row_error:

                logger.exception(
                    f"❌ Review row failed: {row_error}"
                )

                continue

        # ==================================================
        # COMMIT DATABASE
        # ==================================================

        if inserted_reviews:

            await session.commit()

            logger.info(
                f"✅ INSERTED {len(inserted_reviews)} NEW REVIEWS"
            )

        else:

            logger.info(
                "ℹ️ No new reviews found"
            )

        # ==================================================
        # RETURN
        # ==================================================

        return inserted_reviews

    except Exception as e:

        await session.rollback()

        logger.exception(
            f"❌ SCRAPER FAILED: {e}"
        )

        logger.error(
            traceback.format_exc()
        )

        return []
