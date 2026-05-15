# filename: app/services/scraper.py

# ==========================================================
# REVIEW INTELLIGENCE SCRAPER — APIFY + POSTGRESQL INTEGRATED
# ==========================================================

import os
import logging
import asyncio
import re
import json
import requests

from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

from apify_client import ApifyClient

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Company, Review

logger = logging.getLogger("app.scraper")

# ==========================================================
# API CONFIGURATION
# ==========================================================

APIFY_API_TOKEN = os.getenv("APIFY_API_TOKEN")
SERPER_API_KEY = os.getenv("SERPER_API_KEY")

# ==========================================================
# APIFY CLIENT
# ==========================================================

if not APIFY_API_TOKEN:
    logger.warning("⚠️ APIFY_API_TOKEN is missing")

apify_client = ApifyClient(APIFY_API_TOKEN)

# ==========================================================
# SAFE DATETIME
# ==========================================================

def utc_now_naive() -> datetime:

    return datetime.utcnow().replace(tzinfo=None)

# ==========================================================
# RELATIVE DATE PARSER
# ==========================================================

def parse_relative_date(date_text: str) -> datetime:

    if not date_text or not isinstance(date_text, str):
        return utc_now_naive()

    now = utc_now_naive()

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
# SAFE ISO DATE PARSER
# ==========================================================

def safe_parse_iso_datetime(
    date_str: Optional[str]
) -> datetime:

    if not date_str:
        return utc_now_naive()

    try:

        parsed = datetime.fromisoformat(
            date_str.replace("Z", "+00:00")
        )

        return parsed.replace(tzinfo=None)

    except Exception as e:

        logger.warning(
            f"⚠️ Date parse failed: {e}"
        )

        return utc_now_naive()

# ==========================================================
# SERPER FALLBACK
# ==========================================================

async def fetch_from_serper_fallback(
    company_name: str,
    limit: int = 10
) -> List[Dict[str, Any]]:

    logger.info(
        f"📡 Serper fallback for {company_name}"
    )

    if not SERPER_API_KEY:

        logger.error(
            "❌ SERPER_API_KEY missing"
        )

        return []

    url = "https://google.serper.dev/search"

    payload = json.dumps({
        "q": f"{company_name} reviews",
        "gl": "pk",
        "hl": "en"
    })

    headers = {
        "X-API-KEY": SERPER_API_KEY,
        "Content-Type": "application/json"
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

        for idx, entry in enumerate(
            data.get("organic", [])
        ):

            if len(results) >= limit:
                break

            results.append({

                "google_review_id":
                    f"serper_{idx}_{int(utc_now_naive().timestamp())}",

                "author_name":
                    entry.get(
                        "title",
                        "Web Mention"
                    ),

                "rating": 5,

                "text":
                    entry.get(
                        "snippet",
                        "No content"
                    ),

                "google_review_time":
                    utc_now_naive(),

                "review_likes": 0
            })

        return results

    except Exception as e:

        logger.error(
            f"❌ Serper fallback failed: {e}"
        )

        return []

# ==========================================================
# MAIN REVIEW SCRAPER
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
        # LOAD EXISTING REVIEW IDS
        # ==================================================

        if session and company_id:

            stmt = select(
                Review.google_review_id
            ).where(
                Review.company_id == company_id
            )

            res = await session.execute(stmt)

            existing_ids = set(
                res.scalars().all()
            )

            logger.info(
                f"✅ Existing reviews in DB: {len(existing_ids)}"
            )

            comp_stmt = select(
                Company
            ).where(
                Company.id == company_id
            )

            comp_res = await session.execute(
                comp_stmt
            )

            company = comp_res.scalars().first()

            if company:

                company_name = company.name

                place_id = (
                    place_id
                    or company.google_place_id
                )

        # ==================================================
        # VALIDATE PLACE ID
        # ==================================================

        if not place_id:

            logger.error(
                f"❌ No Place ID for {company_name}"
            )

            return []

        logger.info(
            f"🚀 Starting APIFY Sync for {company_name}"
        )

        # ==================================================
        # FETCH EXTRA REVIEWS TO GET NEW UNIQUE REVIEWS
        # ==================================================

        fetch_limit = target_limit + 500

        run_input = {

            "startUrls": [
                {
                    "url":
                    f"https://www.google.com/maps/place/?q=place_id:{place_id}"
                }
            ],

            "maxReviews": fetch_limit,

            "reviewsSort": "newest",

            "reviewsOrigin": "all",

            "language": "en"
        }

        logger.info(
            f"📡 Fetching {fetch_limit} reviews from APIFY"
        )

        # ==================================================
        # RUN APIFY ACTOR
        # ==================================================

        run = await asyncio.to_thread(
            lambda:
            apify_client.actor(
                "compass/google-maps-reviews-scraper"
            ).call(
                run_input=run_input
            )
        )

        dataset_id = run.get(
            "defaultDatasetId"
        )

        if not dataset_id:

            logger.error(
                "❌ No dataset returned from APIFY"
            )

            return []

        logger.info(
            f"✅ APIFY completed | Dataset: {dataset_id}"
        )

        # ==================================================
        # LOAD DATASET ITEMS
        # ==================================================

        dataset_items = await asyncio.to_thread(
            lambda:
            apify_client.dataset(
                dataset_id
            ).list_items().items
        )

        logger.info(
            f"📦 Total Reviews fetched from APIFY: {len(dataset_items)}"
        )

        skipped_duplicates = 0

        # ==================================================
        # PROCESS REVIEWS
        # ==================================================

        for idx, review in enumerate(dataset_items):

            try:

                review_id = (
                    review.get("reviewId")
                    or f"apify_{idx}_{int(utc_now_naive().timestamp())}"
                )

                # ==========================================
                # SKIP EXISTING DATABASE REVIEWS
                # ==========================================

                if review_id in existing_ids:

                    skipped_duplicates += 1
                    continue

                # ==========================================
                # SKIP DUPLICATES IN CURRENT SESSION
                # ==========================================

                if any(
                    r["google_review_id"] == review_id
                    for r in all_reviews
                ):

                    skipped_duplicates += 1
                    continue

                # ==========================================
                # EXTRACT REVIEW DATA
                # ==========================================

                review_text = (
                    review.get("text")
                    or review.get("reviewText")
                    or "No content provided."
                )

                author_name = (
                    review.get("name")
                    or review.get("reviewerName")
                    or "Anonymous"
                )

                try:

                    rating = int(
                        review.get("stars", 5)
                    )

                except:

                    rating = 5

                review_time = safe_parse_iso_datetime(
                    review.get("publishedAtDate")
                )

                likes = review.get(
                    "likesCount",
                    0
                )

                if likes is None:
                    likes = 0

                # ==========================================
                # APPEND CLEAN REVIEW
                # ==========================================

                all_reviews.append({

                    "google_review_id":
                        review_id,

                    "author_name":
                        author_name,

                    "rating":
                        rating,

                    "text":
                        review_text,

                    "google_review_time":
                        review_time,

                    "review_likes":
                        likes
                })

                # ==========================================
                # STOP WHEN TARGET REACHED
                # ==========================================

                if len(all_reviews) >= target_limit:
                    break

            except Exception as review_error:

                logger.error(
                    f"❌ Review processing failed: {review_error}"
                )

                continue

        logger.info(
            f"✅ New unique reviews collected: {len(all_reviews)}"
        )

        logger.info(
            f"⚠️ Duplicate reviews skipped: {skipped_duplicates}"
        )

        return all_reviews

    except Exception as primary_err:

        logger.error(
            f"❌ APIFY sync failed: {primary_err}"
        )

        logger.warning(
            "⚠️ Switching to Serper fallback..."
        )

        return await fetch_from_serper_fallback(
            company_name,
            target_limit
        )

# ==========================================================
# REVIEW SERVICE
# ==========================================================

class ReviewService:

    # ======================================================
    # GET REVIEWS FROM POSTGRESQL
    # ======================================================

    @staticmethod
    async def get_latest_reviews(
        company_id: int,
        limit: int = 100
    ):

        from app.core.db import AsyncSessionLocal

        async with AsyncSessionLocal() as session:

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

                result = await session.execute(stmt)

                reviews = result.scalars().all()

                formatted_reviews = []

                for review in reviews:

                    try:

                        created_at = getattr(
                            review,
                            "google_review_time",
                            None
                        )

                        if created_at:

                            created_at = (
                                created_at.isoformat()
                            )

                        formatted_reviews.append({

                            "id":
                                getattr(
                                    review,
                                    "id",
                                    None
                                ),

                            "author_name":
                                getattr(
                                    review,
                                    "author_name",
                                    "Anonymous"
                                ),

                            "rating":
                                getattr(
                                    review,
                                    "rating",
                                    0
                                ),

                            "text":
                                getattr(
                                    review,
                                    "text",
                                    ""
                                ),

                            "review_text":
                                getattr(
                                    review,
                                    "text",
                                    ""
                                ),

                            "created_at":
                                created_at,

                            "relative_time_description":
                                created_at,

                            "review_likes":
                                getattr(
                                    review,
                                    "review_likes",
                                    0
                                ),

                            "sentiment":
                                (
                                    "positive"
                                    if getattr(
                                        review,
                                        "rating",
                                        0
                                    ) >= 4

                                    else "negative"

                                    if getattr(
                                        review,
                                        "rating",
                                        0
                                    ) <= 2

                                    else "neutral"
                                )
                        })

                    except Exception as row_error:

                        logger.error(
                            f"❌ Review formatting failed: {row_error}"
                        )

                        continue

                logger.info(
                    f"✅ Loaded {len(formatted_reviews)} reviews from PostgreSQL"
                )

                return formatted_reviews

            except Exception as e:

                logger.exception(
                    "❌ Failed loading reviews from PostgreSQL"
                )

                return []

    # ======================================================
    # INGEST REVIEWS INTO POSTGRESQL
    # ======================================================

    @staticmethod
    async def ingest_from_google(
        company_id: int
    ):

        from app.core.db import AsyncSessionLocal

        async with AsyncSessionLocal() as session:

            try:

                company_stmt = select(
                    Company
                ).where(
                    Company.id == company_id
                )

                company_result = await session.execute(
                    company_stmt
                )

                company = company_result.scalars().first()

                if not company:

                    raise Exception(
                        "Company not found"
                    )

                logger.info(
                    f"🚀 Starting sync for: {company.name}"
                )

                reviews = await fetch_reviews_from_google(

                    place_id=
                        company.google_place_id,

                    company_id=
                        company_id,

                    session=
                        session,

                    target_limit=
                        3000
                )

                if not reviews:

                    logger.warning(
                        "⚠️ No reviews fetched"
                    )

                    return {

                        "status": "success",

                        "ingested_count": 0
                    }

                ingested_count = 0

                skipped_existing = 0

                for item in reviews:

                    try:

                        existing_stmt = select(
                            Review
                        ).where(
                            Review.google_review_id
                            ==
                            item["google_review_id"]
                        )

                        existing_result = await session.execute(
                            existing_stmt
                        )

                        existing_review = (
                            existing_result
                            .scalars()
                            .first()
                        )

                        if existing_review:

                            skipped_existing += 1
                            continue

                        author_name = (
                            item.get(
                                "author_name"
                            )
                            or "Anonymous"
                        )

                        rating = (
                            item.get(
                                "rating"
                            )
                            or 5
                        )

                        text = (
                            item.get(
                                "text"
                            )
                            or ""
                        )

                        review_time = (
                            item.get(
                                "google_review_time"
                            )
                            or utc_now_naive()
                        )

                        review_likes = (
                            item.get(
                                "review_likes"
                            )
                            or 0
                        )

                        new_review = Review(

                            company_id=
                                company_id,

                            google_review_id=
                                item.get(
                                    "google_review_id"
                                ),

                            author_name=
                                author_name,

                            rating=
                                rating,

                            text=
                                text,

                            google_review_time=
                                review_time,

                            first_seen_at=
                                utc_now_naive(),

                            review_likes=
                                review_likes
                        )

                        session.add(new_review)

                        ingested_count += 1

                    except Exception as item_error:

                        logger.error(
                            f"❌ Review save failed: {item_error}"
                        )

                        continue

                await session.commit()

                logger.info(
                    f"✅ PostgreSQL ingest complete: {ingested_count}"
                )

                logger.info(
                    f"⚠️ Existing reviews skipped: {skipped_existing}"
                )

                return {

                    "status":
                        "success",

                    "ingested_count":
                        ingested_count,

                    "skipped_existing":
                        skipped_existing
                }

            except Exception as e:

                await session.rollback()

                logger.exception(
                    "❌ PostgreSQL ingest failed"
                )

                return {

                    "status":
                        "error",

                    "ingested_count":
                        0,

                    "message":
                        str(e)
                }
