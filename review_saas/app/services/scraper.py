# ==========================================================
# FILE: app/services/scraper.py
# TRUSTLYTICS AI SaaS - ENTERPRISE REVIEW SCRAPER
# ==========================================================
# FEATURES
# ----------------------------------------------------------
# ✅ Apify Google Reviews Scraper
# ✅ Proxy Support
# ✅ Railway Compatible
# ✅ Async Compatible
# ✅ PostgreSQL Ready
# ✅ Dashboard Ready
# ✅ AI Chatbot Ready
# ✅ Duplicate Protection
# ✅ Stable Production Logging
# ✅ FastAPI Compatible
# ==========================================================

import logging
import asyncio
from datetime import datetime
from typing import List, Dict, Any

from apify_client import ApifyClient

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
# MAIN SCRAPER
# ==========================================================

async def fetch_reviews_from_google(

    place_id: str,

    company_id: int,

    session=None,

    target_limit: int = 100

) -> List[Dict[str, Any]]:

    reviews: List[Dict[str, Any]] = []

    logger.info(
        f"🚀 Starting Apify scraper "
        f"| company_id={company_id}"
    )

    try:

        # ==================================================
        # APIFY TOKEN
        # ==================================================

        from app.core.config import settings

        APIFY_TOKEN = settings.APIFY_TOKEN

        if not APIFY_TOKEN:

            logger.error(
                "❌ APIFY_TOKEN missing"
            )

            return []

        # ==================================================
        # APIFY CLIENT
        # ==================================================

        client = ApifyClient(
            APIFY_TOKEN
        )

        # ==================================================
        # GOOGLE MAPS URL
        # ==================================================

        google_maps_url = (
            f"https://www.google.com/maps/place/"
            f"?q=place_id:{place_id}"
        )

        logger.info(
            f"🌐 Scraping URL: {google_maps_url}"
        )

        # ==================================================
        # APIFY INPUT
        # ==================================================

        run_input = {

            "startUrls": [

                {
                    "url": google_maps_url
                }

            ],

            "language": "en",

            "maxReviews": target_limit,

            "reviewsSort": "newest",

            "reviewsOrigin": "all",

            "personalData": True,

            "maxImages": 0,

            "maxCrawledPlaces": 1,

            "proxy": {

                "useApifyProxy": True,

                "apifyProxyGroups": [
                    "RESIDENTIAL"
                ]
            }
        }

        # ==================================================
        # RUN ACTOR
        # ==================================================

        logger.info(
            "🚀 Launching Apify actor..."
        )

        run = await asyncio.to_thread(

            client.actor(
                "compass/google-maps-reviews-scraper"
            ).call,

            run_input=run_input
        )

        logger.info(
            "✅ Apify actor finished"
        )

        # ==================================================
        # DATASET
        # ==================================================

        dataset_id = run.get(
            "defaultDatasetId"
        )

        if not dataset_id:

            logger.warning(
                "⚠️ No dataset returned"
            )

            return []

        # ==================================================
        # FETCH DATASET ITEMS
        # ==================================================

        dataset_items = await asyncio.to_thread(

            client.dataset(
                dataset_id
            ).list_items
        )

        items = dataset_items.items

        logger.info(
            f"✅ Retrieved {len(items)} reviews"
        )

        # ==================================================
        # PARSE REVIEWS
        # ==================================================

        for item in items:

            try:

                # ==========================================
                # AUTHOR
                # ==========================================

                author_name = (

                    item.get("name")

                    or

                    item.get("reviewerName")

                    or

                    "Anonymous"
                )

                # ==========================================
                # TEXT
                # ==========================================

                text = (

                    item.get("text")

                    or

                    item.get("reviewText")

                    or

                    "No review text"
                )

                # ==========================================
                # RATING
                # ==========================================

                rating = (

                    item.get("stars")

                    or

                    item.get("rating")

                    or

                    5
                )

                try:
                    rating = int(rating)
                except:
                    rating = 5

                # ==========================================
                # REVIEW ID
                # ==========================================

                google_review_id = (

                    item.get("reviewId")

                    or

                    item.get("review_id")

                    or

                    f"{company_id}_{hash(text)}"
                )

                # ==========================================
                # LIKES
                # ==========================================

                review_likes = (

                    item.get("likesCount")

                    or

                    item.get("likes")

                    or

                    0
                )

                # ==========================================
                # DATE
                # ==========================================

                review_time = datetime.utcnow()

                try:

                    published_at = (

                        item.get("publishedAtDate")

                        or

                        item.get("publishedAt")
                    )

                    if published_at:

                        review_time = datetime.fromisoformat(

                            published_at.replace(
                                "Z",
                                "+00:00"
                            )

                        ).replace(tzinfo=None)

                except Exception:
                    pass

                # ==========================================
                # CLEAN TEXT
                # ==========================================

                if len(text) > 5000:
                    text = text[:5000]

                # ==========================================
                # FINAL REVIEW OBJECT
                # ==========================================

                review_data = {

                    "google_review_id":
                        str(google_review_id),

                    "author_name":
                        str(author_name),

                    "rating":
                        rating,

                    "text":
                        str(text),

                    "google_review_time":
                        review_time,

                    "review_likes":
                        int(review_likes)
                }

                reviews.append(
                    review_data
                )

            except Exception as row_error:

                logger.exception(
                    f"❌ Failed parsing review: "
                    f"{row_error}"
                )

                continue

        # ==================================================
        # REMOVE DUPLICATES
        # ==================================================

        unique_reviews = []

        seen = set()

        for review in reviews:

            key = (
                review["author_name"]
                +
                review["text"]
            )

            if key not in seen:

                seen.add(key)

                unique_reviews.append(
                    review
                )

        reviews = unique_reviews

        logger.info(
            f"✅ Final unique reviews: "
            f"{len(reviews)}"
        )

        return reviews

    except Exception as e:

        logger.exception(
            f"❌ Scraper failed: {e}"
        )

        return []
