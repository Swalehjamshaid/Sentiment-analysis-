# filename: app/services/scraper.py
# ==========================================================
# REVIEW INTELLIGENCE SCRAPER — APIFY + DEDUPLICATION
# ==========================================================

import os
import logging
import asyncio
import re
import json
import requests

from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

# APIFY
from apify_client import ApifyClient

# Database dependencies
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Internal models
from app.core.models import Company, Review

logger = logging.getLogger("app.scraper")

# ==========================================================
# API CONFIGURATION
# ==========================================================

# Railway Variables
APIFY_API_TOKEN = os.getenv("APIFY_API_TOKEN")
SERPER_API_KEY = os.getenv("SERPER_API_KEY")

# ==========================================================
# APIFY CLIENT
# ==========================================================

apify_client = ApifyClient(APIFY_API_TOKEN)

# ==========================================================
# UTILITY FUNCTIONS
# ==========================================================

def parse_relative_date(date_text: str) -> datetime:
    """Converts relative dates into datetime"""

    if not date_text or not isinstance(date_text, str):
        return datetime.utcnow()

    now = datetime.utcnow()

    match = re.search(r'(\d+)', date_text)
    quantity = int(match.group(1)) if match else 1

    date_text = date_text.lower()

    if 'second' in date_text:
        return now - timedelta(seconds=quantity)

    elif 'minute' in date_text:
        return now - timedelta(minutes=quantity)

    elif 'hour' in date_text:
        return now - timedelta(hours=quantity)

    elif 'day' in date_text:
        return now - timedelta(days=quantity)

    elif 'week' in date_text:
        return now - timedelta(weeks=quantity)

    elif 'month' in date_text:
        return now - timedelta(days=quantity * 30)

    elif 'year' in date_text:
        return now - timedelta(days=quantity * 365)

    return now

# ==========================================================
# SERPER FALLBACK
# ==========================================================

async def fetch_from_serper_fallback(
    company_name: str,
    limit: int = 10
) -> List[Dict[str, Any]]:

    logger.info(f"📡 Fallback: Serper search for {company_name}")

    if not SERPER_API_KEY:
        logger.error("❌ SERPER_API_KEY missing")
        return []

    url = "https://google.serper.dev/search"

    payload = json.dumps({
        "q": f"{company_name} reviews",
        "gl": "pk",
        "hl": "en"
    })

    headers = {
        'X-API-KEY': SERPER_API_KEY,
        'Content-Type': 'application/json'
    }

    try:

        response = await asyncio.to_thread(
            lambda: requests.post(
                url,
                headers=headers,
                data=payload,
                timeout=20
            )
        )

        response.raise_for_status()

        data = response.json()

        results = []

        for idx, entry in enumerate(data.get("organic", [])):

            if len(results) >= limit:
                break

            results.append({
                "google_review_id": f"serper_{idx}_{int(datetime.utcnow().timestamp())}",
                "author_name": entry.get("title", "Web Mention"),
                "rating": 5,
                "text": entry.get("snippet", "No content"),
                "google_review_time": datetime.utcnow(),
                "review_likes": 0
            })

        return results

    except Exception as e:
        logger.error(f"❌ Serper Fallback Error: {e}")
        return []

# ==========================================================
# MAIN APIFY REVIEW SCRAPER
# ==========================================================

async def fetch_reviews_from_google(
    place_id: Optional[str] = None,
    company_id: Optional[int] = None,
    session: Optional[AsyncSession] = None,
    target_limit: int = 100,
    **kwargs
) -> List[Dict[str, Any]]:

    all_reviews: List[Dict[str, Any]] = []
    existing_ids = set()

    company_name = "Business"

    try:

        # ==================================================
        # LOAD EXISTING DB REVIEWS
        # ==================================================

        if session and company_id:

            stmt = select(Review.google_review_id).where(
                Review.company_id == company_id
            )

            res = await session.execute(stmt)

            existing_ids = set(res.scalars().all())

            comp_stmt = select(Company).where(
                Company.id == company_id
            )

            comp_res = await session.execute(comp_stmt)

            company = comp_res.scalars().first()

            if company:
                company_name = company.name
                place_id = place_id or company.google_place_id

        if not place_id:
            logger.error(f"❌ No Place ID found for {company_name}")
            return []

        logger.info(f"🚀 Starting APIFY Sync for {company_name}")

        # ==================================================
        # APIFY INPUT
        # ==================================================

        run_input = {
            "startUrls": [
                {
                    "url": f"https://www.google.com/maps/place/?q=place_id:{place_id}"
                }
            ],
            "maxReviews": target_limit,
            "reviewsSort": "newest",
            "language": "en"
        }

        # ==================================================
        # RUN APIFY ACTOR
        # ==================================================

        run = await asyncio.to_thread(
            lambda: apify_client.actor(
                "compass/google-maps-reviews-scraper"
            ).call(
                run_input=run_input
            )
        )

        dataset_id = run["defaultDatasetId"]

        logger.info(f"✅ APIFY Run Completed | Dataset: {dataset_id}")

        # ==================================================
        # FETCH DATASET ITEMS
        # ==================================================

        dataset_items = await asyncio.to_thread(
            lambda: apify_client.dataset(
                dataset_id
            ).list_items().items
        )

        # ==================================================
        # PROCESS REVIEWS
        # ==================================================

        for idx, review in enumerate(dataset_items):

            review_id = review.get("reviewId")

            if not review_id:
                review_id = f"apify_{idx}_{int(datetime.utcnow().timestamp())}"

            # DB DUPLICATION CHECK
            if review_id in existing_ids:

                logger.info(
                    f"📍 Existing review reached. DB already synced."
                )

                return all_reviews

            # INTERNAL DUPLICATION CHECK
            if any(
                r["google_review_id"] == review_id
                for r in all_reviews
            ):
                continue

            # REVIEW TEXT
            review_text = (
                review.get("text")
                or review.get("reviewText")
                or "No content provided."
            )

            # AUTHOR
            author_name = (
                review.get("name")
                or review.get("reviewerName")
                or "Anonymous"
            )

            # RATING
            rating = int(review.get("stars", 5))

            # DATE
            review_date = review.get("publishedAtDate")

            if review_date:
                try:
                    review_time = datetime.fromisoformat(
                        review_date.replace("Z", "+00:00")
                    )
                except:
                    review_time = datetime.utcnow()
            else:
                review_time = datetime.utcnow()

            all_reviews.append({
                "google_review_id": review_id,
                "author_name": author_name,
                "rating": rating,
                "text": review_text,
                "google_review_time": review_time,
                "review_likes": review.get("likesCount", 0)
            })

            if len(all_reviews) >= target_limit:
                break

        logger.info(
            f"✅ Total New Reviews Collected: {len(all_reviews)}"
        )

        return all_reviews

    except Exception as primary_err:

        logger.error(
            f"❌ APIFY Primary Path Failed: {primary_err}"
        )

        logger.warning(
            f"⚠️ Falling back to Serper..."
        )

        return await fetch_from_serper_fallback(
            company_name,
            target_limit
        )
