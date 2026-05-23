# ==========================================================
# FILE: app/services/scraper.py
# SERPAPI ONLY — TRUE NEXT 100 REVIEW ENGINE
# STABLE ENTERPRISE VERSION
# MAY 2026
#
# ==========================================================
# FEATURES
# ==========================================================
# ✅ SERPAPI ONLY
# ✅ TRUE NEXT 100 REVIEWS
# ✅ DATABASE MEMORY
# ✅ NO DUPLICATES
# ✅ DATE-WISE EXTRACTION
# ✅ CONTINUOUS PAGINATION
# ✅ FRONTEND SUCCESS RESPONSE
# ✅ RAILWAY SAFE
# ✅ SIMPLE + STABLE
# ==========================================================

import os
import re
import gc
import time
import random
import asyncio
import hashlib
import logging
import traceback
import requests

from datetime import (
    datetime,
    timedelta
)

# ==========================================================
# LOGGER
# ==========================================================

logger = logging.getLogger(
    "app.services.scraper"
)

# ==========================================================
# ENV VARIABLES
# ==========================================================

SERPAPI_API_KEY = os.getenv(
    "SERPAPI_API_KEY"
)

# ==========================================================
# CONFIG
# ==========================================================

REQUEST_TIMEOUT = 120

# ==========================================================
# CLEAN TEXT
# ==========================================================

def clean_text(text):

    if not text:
        return ""

    text = str(text)

    text = text.replace("\n", " ")
    text = text.replace("\r", " ")
    text = text.replace("\t", " ")

    text = " ".join(text.split())

    return text[:5000]

# ==========================================================
# HASH REVIEW
# ==========================================================

def generate_hash(author, text):

    raw = f"{author}_{text}"

    return hashlib.md5(
        raw.encode("utf-8")
    ).hexdigest()

# ==========================================================
# DATE FILTER
# ==========================================================

def passes_date_filter(
    review_date,
    start_date=None
):

    try:

        if not start_date:
            return True

        lower_date = review_date.lower()

        now = datetime.utcnow()

        if "day" in lower_date:

            num = int(
                re.search(
                    r"\d+",
                    lower_date
                ).group()
            )

            actual_date = (
                now - timedelta(days=num)
            )

        elif "week" in lower_date:

            num = int(
                re.search(
                    r"\d+",
                    lower_date
                ).group()
            )

            actual_date = (
                now - timedelta(days=num * 7)
            )

        elif "month" in lower_date:

            num = int(
                re.search(
                    r"\d+",
                    lower_date
                ).group()
            )

            actual_date = (
                now - timedelta(days=num * 30)
            )

        elif "year" in lower_date:

            num = int(
                re.search(
                    r"\d+",
                    lower_date
                ).group()
            )

            actual_date = (
                now - timedelta(days=num * 365)
            )

        else:

            actual_date = now

        return actual_date >= start_date

    except:
        return True

# ==========================================================
# LOAD EXISTING IDS
# ==========================================================

async def load_existing_review_ids(

    db,

    company_id
):

    try:

        query = """

        SELECT review_id
        FROM reviews
        WHERE company_id = ?

        """

        async with db.execute(

            query,

            (company_id,)

        ) as cursor:

            rows = await cursor.fetchall()

        ids = {

            row[0]
            for row in rows
        }

        logger.info(
            f"✅ EXISTING IDS => {len(ids)}"
        )

        return ids

    except Exception as e:

        logger.warning(
            f"⚠️ LOAD IDS FAILED => {e}"
        )

        return set()

# ==========================================================
# SAVE REVIEWS
# ==========================================================

async def save_reviews_to_database(

    db,

    company_id,

    reviews
):

    try:

        if not reviews:
            return 0

        inserted = 0

        for review in reviews:

            try:

                await db.execute(

                    """

                    INSERT OR IGNORE INTO reviews (

                        company_id,
                        review_id,
                        author_name,
                        rating,
                        review_date,
                        text,
                        likes,
                        source

                    )

                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)

                    """,

                    (

                        company_id,

                        review["review_id"],

                        review["author_name"],

                        review["rating"],

                        review["review_date"],

                        review["text"],

                        review["likes"],

                        review["source"]
                    )
                )

                inserted += 1

            except:
                continue

        await db.commit()

        logger.info(
            f"✅ INSERTED => {inserted}"
        )

        return inserted

    except Exception as e:

        logger.warning(
            f"⚠️ SAVE FAILED => {e}"
        )

        return 0

# ==========================================================
# SERPAPI TRUE NEXT REVIEW ENGINE
# ==========================================================

def serpapi_true_next_reviews(

    place_id,

    existing_ids=None,

    target_limit=100,

    start_date=None
):

    logger.info(
        "🚀 SERPAPI TRUE NEXT REVIEW ENGINE STARTED"
    )

    reviews = []

    seen = set()

    existing_ids = existing_ids or set()

    try:

        next_page_token = None

        true_new_reviews = 0

        page_number = 0

        # ==================================================
        # CONTINUE UNTIL TRUE NEW REVIEWS FOUND
        # ==================================================

        while true_new_reviews < target_limit:

            page_number += 1

            logger.info(
                f"📄 PAGE => {page_number}"
            )

            params = {

                "engine":
                    "google_maps_reviews",

                "place_id":
                    place_id,

                "api_key":
                    SERPAPI_API_KEY,

                "sort_by":
                    "newestFirst",

                "hl":
                    "en"
            }

            if next_page_token:

                params[
                    "next_page_token"
                ] = next_page_token

            response = requests.get(

                "https://serpapi.com/search.json",

                params=params,

                timeout=REQUEST_TIMEOUT
            )

            response.raise_for_status()

            data = response.json()

            api_reviews = data.get(
                "reviews",
                []
            )

            # ==================================================
            # NO MORE REVIEWS
            # ==================================================

            if not api_reviews:

                logger.info(
                    "✅ NO MORE REVIEWS AVAILABLE"
                )

                break

            added_this_page = 0

            skipped_duplicates = 0

            for review in api_reviews:

                try:

                    author = clean_text(

                        review.get(
                            "user",
                            {}
                        ).get(
                            "name",
                            ""
                        )
                    )

                    text = clean_text(
                        review.get(
                            "snippet",
                            ""
                        )
                    )

                    if not text:
                        continue

                    review_date = clean_text(
                        review.get(
                            "date",
                            ""
                        )
                    )

                    # ==========================================
                    # DATE FILTER
                    # ==========================================

                    if not passes_date_filter(
                        review_date,
                        start_date
                    ):
                        continue

                    review_id = generate_hash(
                        author,
                        text
                    )

                    # ==========================================
                    # SKIP DUPLICATES
                    # ==========================================

                    if review_id in seen:

                        skipped_duplicates += 1

                        continue

                    # ==========================================
                    # SKIP EXISTING DATABASE REVIEWS
                    # ==========================================

                    if review_id in existing_ids:

                        skipped_duplicates += 1

                        continue

                    seen.add(review_id)

                    # ==========================================
                    # IMPORTANT
                    # UPDATE MEMORY IMMEDIATELY
                    # ==========================================

                    existing_ids.add(review_id)

                    reviews.append({

                        "review_id":
                            review_id,

                        "author_name":
                            author,

                        "rating":
                            review.get(
                                "rating",
                                5
                            ),

                        "review_date":
                            review_date,

                        "text":
                            text,

                        "likes":
                            review.get(
                                "likes",
                                0
                            ),

                        "source":
                            "serpapi"
                    })

                    true_new_reviews += 1

                    added_this_page += 1

                except:
                    continue

            logger.info(
                f"✅ PAGE NEW REVIEWS => {added_this_page}"
            )

            logger.info(
                f"⛔ DUPLICATES SKIPPED => {skipped_duplicates}"
            )

            logger.info(
                f"✅ TOTAL TRUE NEW REVIEWS => {true_new_reviews}"
            )

            # ==================================================
            # TARGET REACHED
            # ==================================================

            if true_new_reviews >= target_limit:

                logger.info(
                    "✅ TARGET TRUE NEW REVIEWS REACHED"
                )

                break

            # ==================================================
            # PAGINATION
            # ==================================================

            next_page_token = (

                data.get(
                    "serpapi_pagination",
                    {}
                ).get(
                    "next_page_token"
                )
            )

            if not next_page_token:

                logger.info(
                    "✅ NO NEXT PAGE TOKEN"
                )

                break

            time.sleep(
                random.uniform(1, 2)
            )

        logger.info(
            f"✅ FINAL TRUE NEW REVIEWS => {len(reviews)}"
        )

        return reviews

    except Exception as e:

        logger.warning(
            f"⚠️ SERPAPI ENGINE FAILED => {e}"
        )

        return []

# ==========================================================
# MAIN ENGINE
# ==========================================================

async def scrape_google_reviews(

    db,

    company_id,

    place_id,

    target_limit=100,

    start_date=None,

    end_date=None
):

    logger.info(
        "🚀 SERPAPI ONLY ENGINE STARTED"
    )

    try:

        # ==================================================
        # LOAD EXISTING DATABASE IDS
        # ==================================================

        existing_review_ids = await load_existing_review_ids(

            db=db,

            company_id=company_id
        )

        logger.info(
            f"✅ EXISTING DB REVIEWS => {len(existing_review_ids)}"
        )

        # ==================================================
        # FETCH TRUE NEW REVIEWS
        # ==================================================

        reviews = await asyncio.to_thread(

            serpapi_true_next_reviews,

            place_id,

            existing_review_ids,

            target_limit,

            start_date
        )

        # ==================================================
        # SAVE TRUE NEW REVIEWS
        # ==================================================

        inserted_count = await save_reviews_to_database(

            db=db,

            company_id=company_id,

            reviews=reviews
        )

        logger.info(
            "✅ FRONTEND SUCCESS RESPONSE SENT"
        )

        # ==================================================
        # RETURN TO FRONTEND
        # ==================================================

        return {

            "success": True,

            "message":
                f"{inserted_count} TRUE NEW REVIEWS ADDED",

            "new_reviews_added":
                inserted_count,

            "reviews":
                reviews[:target_limit]
        }

    except Exception as e:

        logger.exception(
            f"❌ MAIN ENGINE FAILED => {e}"
        )

        logger.error(
            traceback.format_exc()
        )

        return {

            "success": False,

            "message":
                "SCRAPER FAILED",

            "new_reviews_added": 0,

            "reviews": []
        }

    finally:

        gc.collect()
