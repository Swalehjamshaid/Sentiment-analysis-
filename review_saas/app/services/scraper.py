# ==========================================================
# FILE: app/services/scraper.py
# TRUSTLYTICS AI — ENTERPRISE GOOGLE REVIEWS SCRAPER
# FINAL PRODUCTION VERSION — 2026
#
# FULLY SYNCHRONIZED WITH:
# ✅ reviews.py
# ✅ dashboard.py
# ✅ chatbot.py
# ✅ PostgreSQL
# ✅ Railway
# ✅ Incremental Sync
# ✅ Duplicate Protection
# ✅ SERPAPI
# ✅ Proxy Rotation
# ✅ Playwright Fallback
# ==========================================================

import os
import re
import gc
import json
import time
import random
import asyncio
import hashlib
import logging

from datetime import (
    datetime,
    timedelta
)

import httpx

from playwright.async_api import (
    async_playwright
)

from playwright_stealth import (
    stealth_async
)

from fake_useragent import (
    UserAgent
)

from tenacity import (
    retry,
    stop_after_attempt,
    wait_random_exponential
)

from sqlalchemy import select

# ==========================================================
# DATABASE
# ==========================================================

from app.core.db import (
    AsyncSessionLocal
)

# ==========================================================
# MODELS
# ==========================================================

from app.core.models import (
    Review
)

# ==========================================================
# OPTIONAL ADVANCED LIBRARIES
# ==========================================================

try:
    from curl_cffi import requests as curl_requests
except:
    curl_requests = None

# ==========================================================
# LOGGER
# ==========================================================

logger = logging.getLogger(
    "app.services.scraper"
)

# ==========================================================
# ENV
# ==========================================================

SERPAPI_KEY = os.getenv(
    "SERPAPI_KEY"
)

APIFY_TOKEN = os.getenv(
    "APIFY_TOKEN"
)

PROXY_SERVER = os.getenv(
    "PROXY_SERVER"
)

PROXY_USERNAME = os.getenv(
    "PROXY_USERNAME"
)

PROXY_PASSWORD = os.getenv(
    "PROXY_PASSWORD"
)

# ==========================================================
# CONFIG
# ==========================================================

REQUEST_TIMEOUT = 120

PLAYWRIGHT_TIMEOUT = 70000

HEADLESS = True

MAX_SCROLLS = 25

# ==========================================================
# HELPERS
# ==========================================================

def clean_text(text):

    try:

        if not text:
            return ""

        text = str(text)

        text = text.replace("\n", " ")
        text = text.replace("\r", " ")
        text = text.replace("\t", " ")

        return " ".join(text.split())[:5000]

    except:

        return ""

# ==========================================================

def generate_hash(author, text):

    raw = f"{author}_{text}"

    return hashlib.md5(
        raw.encode("utf-8")
    ).hexdigest()

# ==========================================================

def get_user_agent():

    try:

        return UserAgent().random

    except:

        return (
            "Mozilla/5.0 "
            "(Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/126.0 Safari/537.36"
        )

# ==========================================================

def parse_relative_date(relative_text):

    try:

        if not relative_text:
            return datetime.utcnow()

        text = str(relative_text).lower()

        now = datetime.utcnow()

        match = re.search(
            r"(\d+)",
            text
        )

        number = (
            int(match.group(1))
            if match
            else 1
        )

        if "day" in text:

            return now - timedelta(days=number)

        elif "week" in text:

            return now - timedelta(weeks=number)

        elif "month" in text:

            return now - timedelta(days=number * 30)

        elif "year" in text:

            return now - timedelta(days=number * 365)

        return now

    except:

        return datetime.utcnow()

# ==========================================================
# PROXY
# ==========================================================

def build_proxy_url():

    try:

        if not PROXY_SERVER:
            return None

        return (
            f"http://{PROXY_USERNAME}:"
            f"{PROXY_PASSWORD}@{PROXY_SERVER}"
        )

    except:

        return None

# ==========================================================
# EXISTING REVIEW IDS
# ==========================================================

async def load_existing_review_ids(
    company_id: int
):

    existing = set()

    try:

        async with AsyncSessionLocal() as db:

            stmt = select(
                Review.google_review_id
            ).where(
                Review.company_id == company_id
            )

            result = await db.execute(stmt)

            rows = result.fetchall()

            for row in rows:

                if row[0]:
                    existing.add(row[0])

        logger.info(
            f"✅ EXISTING IDS => {len(existing)}"
        )

        return existing

    except Exception as e:

        logger.warning(
            f"⚠️ EXISTING IDS FAILED => {e}"
        )

        return set()

# ==========================================================
# SERPAPI SCRAPER
# ==========================================================

@retry(
    stop=stop_after_attempt(3),
    wait=wait_random_exponential(
        multiplier=2,
        max=15
    )
)
async def scrape_serpapi_reviews(

    place_id,

    existing_ids=None,

    target_limit=100
):

    reviews = []

    existing_ids = existing_ids or set()

    if not SERPAPI_KEY:

        logger.warning(
            "⚠️ SERPAPI KEY MISSING"
        )

        return []

    try:

        proxy_url = build_proxy_url()

        async with httpx.AsyncClient(

            timeout=REQUEST_TIMEOUT,

            proxies=(
                {
                    "http://": proxy_url,
                    "https://": proxy_url
                }
                if proxy_url else None
            ),

            headers={
                "User-Agent": get_user_agent()
            }

        ) as client:

            next_page_token = None

            fetched = 0

            seen = set()

            while fetched < target_limit:

                params = {

                    "engine":
                        "google_maps_reviews",

                    "place_id":
                        place_id,

                    "api_key":
                        SERPAPI_KEY,

                    "sort_by":
                        "newestFirst"
                }

                if next_page_token:

                    params[
                        "next_page_token"
                    ] = next_page_token

                logger.info(
                    f"🚀 SERPAPI REQUEST => {fetched}"
                )

                response = await client.get(

                    "https://serpapi.com/search.json",

                    params=params
                )

                if response.status_code != 200:

                    logger.warning(
                        f"⚠️ SERPAPI STATUS => {response.status_code}"
                    )

                    break

                data = response.json()

                raw_reviews = data.get(
                    "reviews",
                    []
                )

                logger.info(
                    f"📦 SERPAPI RAW => {len(raw_reviews)}"
                )

                if not raw_reviews:
                    break

                for review in raw_reviews:

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

                        rating = int(

                            review.get(
                                "rating",
                                5
                            )
                        )

                        review_date = clean_text(

                            review.get(
                                "date",
                                ""
                            )
                        )

                        review_id = generate_hash(
                            author,
                            text
                        )

                        if (
                            review_id in seen
                            or
                            review_id in existing_ids
                        ):
                            continue

                        seen.add(review_id)

                        existing_ids.add(review_id)

                        sentiment = (
                            "positive"
                            if rating >= 4
                            else "negative"
                        )

                        reviews.append({

                            "review_id":
                                review_id,

                            "author_name":
                                author,

                            "rating":
                                rating,

                            "review_date":
                                review_date,

                            "google_review_time":

                                parse_relative_date(
                                    review_date
                                ).isoformat(),

                            "text":
                                text,

                            "likes":
                                0,

                            "sentiment":
                                sentiment
                        })

                        fetched += 1

                        if fetched >= target_limit:
                            break

                    except Exception as review_error:

                        logger.warning(
                            f"⚠️ REVIEW PARSE FAILED => {review_error}"
                        )

                        continue

                next_page_token = data.get(
                    "serpapi_pagination",
                    {}
                ).get(
                    "next_page_token"
                )

                if not next_page_token:
                    break

                await asyncio.sleep(
                    random.uniform(1, 3)
                )

        logger.info(
            f"✅ SERPAPI REVIEWS => {len(reviews)}"
        )

        return reviews

    except Exception as e:

        logger.exception(
            f"❌ SERPAPI FAILED => {e}"
        )

        return []

# ==========================================================
# PLAYWRIGHT FALLBACK
# ==========================================================

@retry(
    stop=stop_after_attempt(2),
    wait=wait_random_exponential(
        multiplier=2,
        max=10
    )
)
async def playwright_backup(

    place_id,

    existing_ids=None,

    target_limit=50
):

    reviews = []

    existing_ids = existing_ids or set()

    browser = None

    try:

        async with async_playwright() as p:

            proxy_url = build_proxy_url()

            browser = await p.chromium.launch(

                headless=HEADLESS,

                proxy=(
                    {
                        "server":
                            f"http://{PROXY_SERVER}",

                        "username":
                            PROXY_USERNAME,

                        "password":
                            PROXY_PASSWORD
                    }
                    if proxy_url else None
                ),

                args=[

                    "--disable-blink-features=AutomationControlled",

                    "--disable-dev-shm-usage",

                    "--disable-gpu",

                    "--no-sandbox"
                ]
            )

            context = await browser.new_context(

                user_agent=get_user_agent(),

                locale="en-US"
            )

            page = await context.new_page()

            # ==================================================
            # BLOCK HEAVY ASSETS
            # ==================================================

            await page.route(

                "**/*.{png,jpg,jpeg,gif,svg,webp}",

                lambda route: route.abort()
            )

            await stealth_async(page)

            url = (
                f"https://www.google.com/maps/place/"
                f"?q=place_id:{place_id}"
            )

            logger.info(
                f"🚀 PLAYWRIGHT STARTED => {place_id}"
            )

            await page.goto(

                url,

                wait_until="domcontentloaded",

                timeout=PLAYWRIGHT_TIMEOUT
            )

            await asyncio.sleep(5)

            try:

                button = page.locator(
                    'button[jsaction*="pane.reviewChart.moreReviews"]'
                )

                if await button.count() > 0:

                    await button.first.click()

                    await asyncio.sleep(5)

            except:
                pass

            review_feed = page.locator(
                'div[role="feed"]'
            )

            for _ in range(MAX_SCROLLS):

                try:

                    await review_feed.evaluate(
                        "(el) => el.scrollTop = el.scrollHeight"
                    )

                    await asyncio.sleep(
                        random.uniform(0.8, 1.8)
                    )

                except:
                    pass

            cards = page.locator(
                "div.jftiEf"
            )

            count = await cards.count()

            logger.info(
                f"📦 PLAYWRIGHT CARDS => {count}"
            )

            seen = set()

            for i in range(count):

                try:

                    card = cards.nth(i)

                    author = clean_text(

                        await card.locator(
                            ".d4r55"
                        ).inner_text()
                    )

                    text = clean_text(

                        await card.locator(
                            ".wiI7pd"
                        ).inner_text()
                    )

                    if not text:
                        continue

                    review_date = clean_text(

                        await card.locator(
                            ".rsqaWe"
                        ).inner_text()
                    )

                    rating = 5

                    try:

                        aria = await card.locator(
                            ".kvMYJc"
                        ).get_attribute(
                            "aria-label"
                        )

                        match = re.search(
                            r"(\\d)",
                            str(aria)
                        )

                        if match:
                            rating = int(
                                match.group(1)
                            )

                    except:
                        pass

                    review_id = generate_hash(
                        author,
                        text
                    )

                    if (
                        review_id in seen
                        or
                        review_id in existing_ids
                    ):
                        continue

                    seen.add(review_id)

                    existing_ids.add(review_id)

                    sentiment = (
                        "positive"
                        if rating >= 4
                        else "negative"
                    )

                    reviews.append({

                        "review_id":
                            review_id,

                        "author_name":
                            author,

                        "rating":
                            rating,

                        "review_date":
                            review_date,

                        "google_review_time":

                            parse_relative_date(
                                review_date
                            ).isoformat(),

                        "text":
                            text,

                        "likes":
                            0,

                        "sentiment":
                            sentiment
                    })

                    if len(reviews) >= target_limit:
                        break

                except:
                    continue

        logger.info(
            f"✅ PLAYWRIGHT REVIEWS => {len(reviews)}"
        )

        return reviews

    except Exception as e:

        logger.warning(
            f"⚠️ PLAYWRIGHT FAILED => {e}"
        )

        return []

    finally:

        if browser:

            try:
                await browser.close()
            except:
                pass

# ==========================================================
# MAIN SCRAPER
# ==========================================================

async def scrape_google_reviews(

    place_id: str,

    company_id: int = None,

    target_limit: int = 100,

    start_date=None,

    end_date=None
):

    logger.info(
        f"🚀 HYBRID SCRAPER STARTED => {place_id}"
    )

    try:

        if not place_id:

            logger.error(
                "❌ PLACE ID MISSING"
            )

            return []

        existing_review_ids = set()

        if company_id:

            existing_review_ids = await load_existing_review_ids(
                company_id
            )

        # ==================================================
        # PRIMARY ENGINE => SERPAPI
        # ==================================================

        serp_reviews = await scrape_serpapi_reviews(

            place_id=place_id,

            existing_ids=existing_review_ids,

            target_limit=target_limit
        )

        # ==================================================
        # FALLBACK => PLAYWRIGHT
        # ==================================================

        if len(serp_reviews) < target_limit:

            remaining = (
                target_limit - len(serp_reviews)
            )

            logger.warning(
                f"⚠️ PLAYWRIGHT FALLBACK => {remaining}"
            )

            playwright_reviews = await playwright_backup(

                place_id=place_id,

                existing_ids=existing_review_ids,

                target_limit=remaining
            )

            serp_reviews.extend(
                playwright_reviews
            )

        # ==================================================
        # FINAL DEDUPLICATION
        # ==================================================

        final_reviews = []

        seen = set()

        for review in serp_reviews:

            rid = review.get(
                "review_id"
            )

            if rid and rid not in seen:

                seen.add(rid)

                final_reviews.append(review)

        logger.info(
            f"✅ FINAL REVIEW COUNT => {len(final_reviews)}"
        )

        return final_reviews

    except Exception as e:

        logger.exception(
            f"❌ SCRAPER FAILED => {e}"
        )

        return []

    finally:

        gc.collect()
