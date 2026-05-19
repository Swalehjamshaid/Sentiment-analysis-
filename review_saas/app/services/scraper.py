# ==========================================================
# FILE: app/services/scraper.py
# TRUSTLYTICS AI SAAS - FINAL ENTERPRISE SCRAPER
# ==========================================================
#
# FEATURES
# ----------------------------------------------------------
# ✅ APIFY GOOGLE REVIEWS SCRAPER
# ✅ PostgreSQL Integration
# ✅ Dashboard Compatible
# ✅ Async SQLAlchemy
# ✅ Duplicate Protection
# ✅ Existing Review Comparison
# ✅ Review Persistence
# ✅ Railway Compatible
# ✅ FastAPI Compatible
# ✅ AI Chatbot Compatible
# ✅ Sentiment Scoring
# ✅ Structured Logging
# ✅ Safe Parsing
# ✅ Production Ready
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
from app.core.config import settings

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
# HASH GENERATOR
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
# APIFY CLIENT
# ==========================================================

def create_apify_client():

    token = getattr(
        settings,
        "APIFY_TOKEN",
        None
    )

    if not token:

        raise ValueError(
            "❌ APIFY_TOKEN missing"
        )

    return ApifyClient(token)

# ==========================================================
# GOOGLE MAPS URL
# ==========================================================

def build_google_maps_url(
    place_id: str
):

    return (
        "https://www.google.com/maps/place/"
        f"?q=place_id:{place_id}"
    )

# ==========================================================
# APIFY INPUT
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

    session: AsyncSession,

    company_id: int

):

    stmt = select(
        Review.google_review_id
    ).where(
        Review.company_id == company_id
    )

    result = await session.execute(
        stmt
    )

    rows = result.scalars().all()

    return set(rows)

# ==========================================================
# NORMALIZE REVIEW
# ==========================================================

def normalize_review(

    item: Dict[str, Any],

    company_id: int

):

    try:

        # ==================================================
        # AUTHOR
        # ==================================================

        author_name = (

            item.get("name")

            or

            item.get("reviewerName")

            or

            item.get("authorName")

            or

            "Anonymous"
        )

        author_name = safe_string(
            author_name,
            "Anonymous"
        )

        # ==================================================
        # REVIEW TEXT
        # ==================================================

        review_text = (

            item.get("text")

            or

            item.get("reviewText")

            or

            item.get("review")

            or

            "No review text"
        )

        review_text = clean_review_text(
            review_text
        )

        # ==================================================
        # RATING
        # ==================================================

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

        if rating < 1:
            rating = 1

        if rating > 5:
            rating = 5

        # ==================================================
        # LIKES
        # ==================================================

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

        # ==================================================
        # REVIEW DATE
        # ==================================================

        review_time = (

            item.get("publishedAtDate")

            or

            item.get("publishedAt")

            or

            item.get("date")
        )

        review_time = safe_datetime(
            review_time
        )

        # ==================================================
        # REVIEW ID
        # ==================================================

        google_review_id = (

            item.get("reviewId")

            or

            item.get("review_id")
        )

        if not google_review_id:

            google_review_id = (

                f"{company_id}_"

                f"{generate_hash(author_name, review_text)}"
            )

        google_review_id = safe_string(
            google_review_id
        )

        # ==================================================
        # SENTIMENT SCORE
        # ==================================================

        sentiment_score = round(
            rating / 5,
            2
        )

        # ==================================================
        # NORMALIZED OBJECT
        # ==================================================

        normalized = {

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

        return normalized

    except Exception as e:

        logger.exception(
            f"❌ Normalize failed: {e}"
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
        f"🚀 ENTERPRISE SCRAPER STARTED | company_id={company_id}"
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
        # EXISTING DB REVIEWS
        # ==================================================

        existing_ids = await get_existing_review_ids(

            session=session,

            company_id=company_id
        )

        logger.info(
            f"📦 Existing DB reviews: {len(existing_ids)}"
        )

        # ==================================================
        # APIFY CLIENT
        # ==================================================

        client = create_apify_client()

        # ==================================================
        # GOOGLE MAPS URL
        # ==================================================

        google_maps_url = build_google_maps_url(
            place_id
        )

        logger.info(
            f"🌐 Target URL: {google_maps_url}"
        )

        # ==================================================
        # APIFY INPUT
        # ==================================================

        actor_input = build_actor_input(

            google_maps_url=
                google_maps_url,

            target_limit=
                target_limit
        )

        # ==================================================
        # RUN APIFY ACTOR
        # ==================================================

        logger.info(
            "🚀 Starting APIFY actor..."
        )

        run = await asyncio.to_thread(

            client.actor(
                "compass/google-maps-reviews-scraper"
            ).call,

            run_input=actor_input
        )

        if not run:

            logger.error(
                "❌ Actor execution failed"
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

                    item=item,

                    company_id=company_id
                )

                if not normalized:
                    continue

                google_review_id = normalized.get(
                    "google_review_id"
                )

                if not google_review_id:
                    continue

                # ==========================================
                # EXISTING DB CHECK
                # ==========================================

                if google_review_id in existing_ids:
                    continue

                # ==========================================
                # MEMORY DUPLICATE CHECK
                # ==========================================

                memory_key = generate_hash(

                    normalized["author_name"],

                    normalized["text"]
                )

                if memory_key in memory_hashes:
                    continue

                memory_hashes.add(
                    memory_key
                )

                # ==========================================
                # CREATE REVIEW OBJECT
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

                    review_likes=
                        normalized["review_likes"],

                    first_seen_at=
                        datetime.utcnow(),

                    created_at=
                        datetime.utcnow()
                )

                # ==========================================
                # ADD TO DATABASE
                # ==========================================

                session.add(
                    new_review
                )

                inserted_reviews.append(
                    normalized
                )

            except Exception as row_error:

                logger.exception(
                    f"❌ Row processing failed: {row_error}"
                )

                continue

        # ==================================================
        # COMMIT DATABASE
        # ==================================================

        if inserted_reviews:

            await session.commit()

            logger.info(
                f"✅ INSERTED {len(inserted_reviews)} REVIEWS"
            )

        else:

            logger.info(
                "ℹ️ No new reviews found"
            )

        # ==================================================
        # RETURN INSERTED REVIEWS
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
