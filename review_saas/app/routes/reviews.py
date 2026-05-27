# =========================================================
# FILE: app/services/scraper.py
# TRUSTLYTICS AI - ENTERPRISE PRODUCTION SCRAPER
# FULLY ALIGNED WITH reviews.py
# RAILWAY SAFE • LOW MEMORY • ASYNC • FRONTEND SAFE
# =========================================================

from __future__ import annotations

# =========================================================
# STANDARD LIBRARIES
# =========================================================

import os
import re
import json
import time
import random
import asyncio
import hashlib
import logging
import traceback

from datetime import datetime
from typing import (
    List,
    Dict,
    Any,
    Optional
)

# =========================================================
# REQUESTS
# =========================================================

import requests

# =========================================================
# TENACITY
# =========================================================

from tenacity import (
    retry,
    stop_after_attempt,
    wait_random_exponential
)

# =========================================================
# CACHE
# =========================================================

from cachetools import TTLCache

# =========================================================
# PLAYWRIGHT
# =========================================================

PLAYWRIGHT_AVAILABLE = False

try:

    from playwright.async_api import (
        async_playwright,
        TimeoutError as PlaywrightTimeoutError
    )

    PLAYWRIGHT_AVAILABLE = True

except Exception as e:

    print(f"❌ PLAYWRIGHT IMPORT ERROR => {e}")

# =========================================================
# PLAYWRIGHT STEALTH
# =========================================================

STEALTH_AVAILABLE = False

try:

    from playwright_stealth import stealth_async

    STEALTH_AVAILABLE = True

except Exception as e:

    print(f"❌ PLAYWRIGHT STEALTH ERROR => {e}")

# =========================================================
# SELECTOLAX
# =========================================================

SELECTOLAX_AVAILABLE = False

try:

    from selectolax.parser import HTMLParser

    SELECTOLAX_AVAILABLE = True

except Exception as e:

    print(f"❌ SELECTOLAX ERROR => {e}")

# =========================================================
# LOGGER
# =========================================================

logger = logging.getLogger(__name__)

logger.setLevel(logging.INFO)

# =========================================================
# ENVIRONMENT
# =========================================================

SERPAPI_KEY = os.getenv(
    "SERPAPI_KEY",
    ""
).strip()

SCRAPER_TIMEOUT = int(
    os.getenv(
        "SCRAPER_TIMEOUT",
        "120"
    )
)

MAX_REVIEWS = int(
    os.getenv(
        "SCRAPER_MAX_REVIEWS",
        "100"
    )
)

HEADLESS_MODE = os.getenv(
    "SCRAPER_HEADLESS",
    "true"
).lower() == "true"

PROXY_SERVER = os.getenv(
    "PROXY_SERVER",
    ""
).strip()

PROXY_USERNAME = os.getenv(
    "PROXY_USERNAME",
    ""
).strip()

PROXY_PASSWORD = os.getenv(
    "PROXY_PASSWORD",
    ""
).strip()

# =========================================================
# CACHE
# =========================================================

review_cache = TTLCache(
    maxsize=500,
    ttl=3600
)

# =========================================================
# CONCURRENCY PROTECTION
# =========================================================

SCRAPER_SEMAPHORE = asyncio.Semaphore(2)

# =========================================================
# HELPERS
# =========================================================

def utc_now():

    return datetime.utcnow()


def maps_url(
    place_id: str
):

    return (
        "https://www.google.com/maps/place/"
        f"?q=place_id:{place_id}"
    )


def get_user_agent():

    user_agents = [

        (
            "Mozilla/5.0 "
            "(Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/125.0 Safari/537.36"
        ),

        (
            "Mozilla/5.0 "
            "(Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/124.0 Safari/537.36"
        )
    ]

    return random.choice(user_agents)


async def human_delay(
    minimum=1,
    maximum=3
):

    await asyncio.sleep(
        random.uniform(
            minimum,
            maximum
        )
    )

# =========================================================
# REVIEW ID
# =========================================================

def generate_review_id(
    place_id: str,
    author: str,
    text: str
):

    raw = f"{place_id}:{author}:{text}"

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()

# =========================================================
# NORMALIZER
# =========================================================

def normalize_review(
    review: Dict[str, Any],
    place_id: str
):

    try:

        review_text = str(

            review.get(
                "review_text",

                review.get(
                    "text",

                    review.get(
                        "content",
                        ""
                    )
                )
            )

        ).strip()

        if not review_text:

            return None

        author = str(

            review.get(
                "author",

                review.get(
                    "author_name",
                    "Anonymous"
                )
            )

        ).strip()

        if not author:

            author = "Anonymous"

        rating = review.get(
            "rating",
            5
        )

        try:

            rating = int(float(rating))

        except Exception:

            rating = 5

        if rating < 1:
            rating = 1

        if rating > 5:
            rating = 5

        return {

            "google_review_id":
                generate_review_id(
                    place_id,
                    author,
                    review_text
                ),

            "author":
                author,

            "author_name":
                author,

            "rating":
                rating,

            "review_text":
                review_text,

            "content":
                review_text,

            "text":
                review_text,

            "sentiment_score":
                0.5,

            "google_review_time":
                utc_now(),

            "scraped_at":
                utc_now()
        }

    except Exception as e:

        logger.error(
            f"❌ NORMALIZE ERROR => {e}"
        )

        return None

# =========================================================
# DEDUPLICATION
# =========================================================

def deduplicate_reviews(
    reviews: List[Dict]
):

    unique_reviews = []

    seen = set()

    for review in reviews:

        review_id = review.get(
            "google_review_id",
            ""
        )

        if not review_id:

            continue

        if review_id in seen:

            continue

        seen.add(review_id)

        unique_reviews.append(review)

    return unique_reviews

# =========================================================
# SERPAPI PROVIDER
# =========================================================

@retry(
    stop=stop_after_attempt(3),
    wait=wait_random_exponential(
        min=2,
        max=10
    ),
    reraise=True
)
def serpapi_reviews(
    place_id: str
):

    reviews = []

    if not SERPAPI_KEY:

        logger.warning(
            "⚠️ SERPAPI KEY MISSING"
        )

        return reviews

    try:

        response = requests.get(

            "https://serpapi.com/search.json",

            params={

                "engine":
                    "google_maps_reviews",

                "place_id":
                    place_id,

                "api_key":
                    SERPAPI_KEY,

                "hl":
                    "en"
            },

            timeout=SCRAPER_TIMEOUT
        )

        if response.status_code != 200:

            logger.error(
                f"❌ SERPAPI STATUS => {response.status_code}"
            )

            return reviews

        data = response.json()

        raw_reviews = data.get(
            "reviews",
            []
        )

        if not isinstance(
            raw_reviews,
            list
        ):

            raw_reviews = []

        for item in raw_reviews:

            normalized = normalize_review({

                "author":
                    item.get(
                        "user",
                        "Google User"
                    ),

                "rating":
                    item.get(
                        "rating",
                        5
                    ),

                "review_text":
                    item.get(
                        "snippet",
                        ""
                    )

            }, place_id)

            if normalized:

                reviews.append(
                    normalized
                )

    except Exception as e:

        logger.error(
            f"❌ SERPAPI ERROR => {e}"
        )

    return reviews

# =========================================================
# PLAYWRIGHT PROVIDER
# =========================================================

async def playwright_reviews(
    place_id: str
):

    reviews = []

    if not PLAYWRIGHT_AVAILABLE:

        return reviews

    async with SCRAPER_SEMAPHORE:

        browser = None

        try:

            async with async_playwright() as p:

                browser = await p.chromium.launch(

                    headless=HEADLESS_MODE,

                    args=[

                        "--disable-blink-features=AutomationControlled",

                        "--no-sandbox",

                        "--disable-dev-shm-usage",

                        "--disable-gpu"
                    ]
                )

                context = await browser.new_context(

                    user_agent=get_user_agent(),

                    locale="en-US",

                    viewport={

                        "width": 1280,
                        "height": 900
                    }
                )

                page = await context.new_page()

                if STEALTH_AVAILABLE:

                    try:

                        await stealth_async(page)

                    except Exception:
                        pass

                await page.goto(

                    maps_url(place_id),

                    wait_until="domcontentloaded",

                    timeout=90000
                )

                await human_delay()

                review_button_selectors = [

                    'button[jsaction*="pane.reviewChart.moreReviews"]',

                    'button[aria-label*="reviews"]',

                    'button[aria-label*="Reviews"]'
                ]

                for selector in review_button_selectors:

                    try:

                        locator = page.locator(
                            selector
                        ).first

                        if await locator.count() > 0:

                            await locator.click()

                            break

                    except Exception:
                        continue

                await page.wait_for_timeout(
                    4000
                )

                review_panel = page.locator(
                    "div.m6QErb"
                ).nth(1)

                previous_count = 0

                for _ in range(15):

                    try:

                        await review_panel.hover()

                        await review_panel.evaluate(
                            "(el) => el.scrollTop = el.scrollHeight"
                        )

                        await human_delay(
                            1,
                            2
                        )

                        review_cards = await page.locator(
                            "div.jftiEf"
                        ).count()

                        if review_cards == previous_count:

                            break

                        previous_count = review_cards

                    except Exception:
                        break

                review_elements = page.locator(
                    "div.jftiEf"
                )

                total_elements = await review_elements.count()

                total_elements = min(
                    total_elements,
                    MAX_REVIEWS
                )

                for index in range(total_elements):

                    try:

                        item = review_elements.nth(index)

                        author = "Anonymous"
                        text = ""
                        rating = 5

                        try:

                            author_locator = item.locator(
                                ".d4r55"
                            )

                            if await author_locator.count() > 0:

                                author = (
                                    await author_locator
                                    .inner_text()
                                ).strip()

                        except Exception:
                            pass

                        try:

                            text_locator = item.locator(
                                ".wiI7pd"
                            )

                            if await text_locator.count() > 0:

                                text = (
                                    await text_locator
                                    .inner_text()
                                ).strip()

                        except Exception:
                            pass

                        try:

                            rating_locator = item.locator(
                                "span.kvMYJc"
                            )

                            if await rating_locator.count() > 0:

                                aria = await rating_locator.get_attribute(
                                    "aria-label"
                                )

                                if aria:

                                    match = re.search(
                                        r"(\d)",
                                        aria
                                    )

                                    if match:

                                        rating = int(
                                            match.group(1)
                                        )

                        except Exception:
                            pass

                        normalized = normalize_review({

                            "author":
                                author,

                            "rating":
                                rating,

                            "review_text":
                                text

                        }, place_id)

                        if normalized:

                            reviews.append(
                                normalized
                            )

                    except Exception:
                        continue

        except Exception as e:

            logger.error(
                f"❌ PLAYWRIGHT ERROR => {e}"
            )

            logger.error(
                traceback.format_exc()
            )

        finally:

            try:

                if browser:

                    await browser.close()

            except Exception:
                pass

    return reviews

# =========================================================
# MASTER SCRAPER
# =========================================================

async def scrape_google_reviews(
    place_id: str
):

    logger.info(
        f"🚀 SCRAPER STARTED => {place_id}"
    )

    if not place_id:

        return []

    cache_key = f"reviews:{place_id}"

    try:

        cached = review_cache.get(
            cache_key
        )

        if cached:

            logger.info(
                "⚡ CACHE HIT"
            )

            return cached

    except Exception:
        pass

    all_reviews = []

    providers = [

        (
            "serpapi",
            lambda: asyncio.to_thread(
                serpapi_reviews,
                place_id
            )
        ),

        (
            "playwright",
            lambda: playwright_reviews(
                place_id
            )
        )
    ]

    for provider_name, provider in providers:

        try:

            logger.info(
                f"🔥 PROVIDER => {provider_name}"
            )

            result = await provider()

            if not isinstance(
                result,
                list
            ):

                logger.warning(
                    f"⚠️ INVALID RESULT TYPE => {provider_name}"
                )

                continue

            if result:

                all_reviews.extend(
                    result
                )

            logger.info(
                f"✅ {provider_name} => {len(result)}"
            )

            if len(all_reviews) >= MAX_REVIEWS:

                break

        except Exception as provider_error:

            logger.error(
                f"❌ PROVIDER FAILED => {provider_name}"
            )

            logger.error(
                str(provider_error)
            )

    all_reviews = deduplicate_reviews(
        all_reviews
    )

    all_reviews = all_reviews[:MAX_REVIEWS]

    try:

        review_cache[
            cache_key
        ] = all_reviews

    except Exception:
        pass

    logger.info(
        f"✅ FINAL REVIEWS => {len(all_reviews)}"
    )

    # IMPORTANT:
    # RETURNS ONLY LIST
    # FULLY ALIGNED WITH reviews.py

    return all_reviews

# =========================================================
# ALIAS
# =========================================================

async def run_scraper(
    place_id: str
):

    return await scrape_google_reviews(
        place_id
    )

# =========================================================
# READY
# =========================================================

logger.info(
    "✅ ENTERPRISE SCRAPER READY"
)
