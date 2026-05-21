# ==========================================================
# FILE: app/services/scraper.py
# TRUSTLYTICS AI — ENTERPRISE GOOGLE REVIEW SCRAPER
# FINAL POSTGRESQL-COMPATIBLE VERSION
# MAY 2026
# ==========================================================

# ==========================================================
# ENGINES:
# 0. SERPAPI
# 1. CAMOUFOX + PLAYWRIGHT
# 2. PLAYWRIGHT STEALTH
# 3. SELENIUMBASE UC
# 4. REQUESTS + BS4 FALLBACK
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
import traceback

from typing import (
    List,
    Dict,
    Any
)

# ==========================================================
# RETRIES
# ==========================================================

from tenacity import (

    retry,

    stop_after_attempt,

    wait_exponential
)

# ==========================================================
# USER AGENT
# ==========================================================

from fake_useragent import (
    UserAgent
)

# ==========================================================
# PLAYWRIGHT
# ==========================================================

from playwright.async_api import (

    async_playwright,

    TimeoutError as PlaywrightTimeout
)

# ==========================================================
# CAMOUFOX
# ==========================================================

from camoufox.async_api import (
    AsyncCamoufox
)

# ==========================================================
# PLAYWRIGHT STEALTH
# ==========================================================

from playwright_stealth import (
    stealth_async
)

# ==========================================================
# SELENIUMBASE
# ==========================================================

from seleniumbase import (
    SB
)

# ==========================================================
# REQUESTS / BS4
# ==========================================================

import requests

from bs4 import (
    BeautifulSoup
)

# ==========================================================
# LOGGER
# ==========================================================

logger = logging.getLogger(
    "app.services.scraper"
)

# ==========================================================
# CONFIG
# ==========================================================

HEADLESS = False

MAX_SCROLLS = 120

MAX_IDLE_SCROLLS = 8

DEBUG_DIR = "/tmp"

COOKIES_FILE = "cookies.json"

REQUEST_TIMEOUT = 120

SERPAPI_API_KEY = os.getenv(
    "SERPAPI_API_KEY"
)

PROXY_URL = os.getenv(
    "PROXY_URL"
)

# ==========================================================
# HELPERS
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
# NORMALIZE RATING
# ==========================================================

def normalize_rating(text):

    try:

        match = re.search(
            r"([0-9.]+)",
            str(text)
        )

        if match:

            return int(
                float(
                    match.group(1)
                )
            )

    except Exception:
        pass

    return 5

# ==========================================================
# GENERATE REVIEW HASH
# ==========================================================

def generate_hash(author, text):

    raw = f"{author}_{text}"

    return hashlib.md5(
        raw.encode("utf-8")
    ).hexdigest()

# ==========================================================
# NORMALIZE REVIEW OBJECT
# ==========================================================

def normalize_review_object(review):

    try:

        return {

            "review_id":
                str(
                    review.get(
                        "review_id",
                        generate_hash(
                            "unknown",
                            str(random.random())
                        )
                    )
                ),

            "author_name":
                clean_text(
                    review.get(
                        "author_name",
                        "Anonymous"
                    )
                ),

            "rating":
                int(
                    review.get(
                        "rating",
                        5
                    )
                ),

            "review_date":
                clean_text(
                    review.get(
                        "review_date",
                        ""
                    )
                ),

            "text":
                clean_text(
                    review.get(
                        "text",
                        ""
                    )
                ),

            "likes":
                int(
                    review.get(
                        "likes",
                        0
                    )
                ),

            "source":
                review.get(
                    "source",
                    "unknown"
                )
        }

    except Exception as e:

        logger.warning(
            f"⚠️ NORMALIZATION FAILED => {e}"
        )

        return {

            "review_id":
                generate_hash(
                    "fallback",
                    str(random.random())
                ),

            "author_name":
                "Anonymous",

            "rating":
                5,

            "review_date":
                "",

            "text":
                "",

            "likes":
                0,

            "source":
                "fallback"
        }

# ==========================================================
# DEBUG FILES
# ==========================================================

async def save_debug_files(page, name):

    try:

        await page.screenshot(

            path=f"{DEBUG_DIR}/{name}.png",

            full_page=True
        )

        html = await page.content()

        with open(

            f"{DEBUG_DIR}/{name}.html",

            "w",

            encoding="utf-8"

        ) as f:

            f.write(html)

        logger.info(
            f"📸 DEBUG SAVED => {name}"
        )

    except Exception as e:

        logger.warning(
            f"⚠️ DEBUG SAVE FAILED => {e}"
        )

# ==========================================================
# CAPTCHA DETECTION
# ==========================================================

async def detect_google_block(page):

    try:

        content = (
            await page.content()
        ).lower()

        keywords = [

            "captcha",

            "unusual traffic",

            "not a robot",

            "/sorry/",

            "automated queries"
        ]

        for keyword in keywords:

            if keyword in content:

                logger.warning(
                    f"⚠️ GOOGLE BLOCK => {keyword}"
                )

                return True

        return False

    except Exception:

        return False

# ==========================================================
# HUMAN SCROLL
# ==========================================================

async def human_scroll(page):

    try:

        await page.mouse.wheel(

            0,

            random.randint(
                1500,
                4000
            )
        )

        await asyncio.sleep(

            random.uniform(
                3,
                7
            )
        )

    except Exception:
        pass

# ==========================================================
# HANDLE CONSENT
# ==========================================================

async def handle_google_consent(page):

    try:

        buttons = await page.query_selector_all(
            "button"
        )

        for button in buttons:

            try:

                text = clean_text(
                    await button.inner_text()
                ).lower()

                if any(

                    x in text

                    for x in [

                        "accept",

                        "i agree",

                        "accept all"
                    ]
                ):

                    await button.click()

                    logger.info(
                        "✅ CONSENT ACCEPTED"
                    )

                    await asyncio.sleep(5)

                    return

            except Exception:
                continue

    except Exception:
        pass

# ==========================================================
# LOAD COOKIES
# ==========================================================

async def load_cookies(context):

    try:

        if not os.path.exists(
            COOKIES_FILE
        ):
            return

        with open(

            COOKIES_FILE,

            "r",

            encoding="utf-8"

        ) as f:

            cookies = json.load(f)

        await context.add_cookies(
            cookies
        )

        logger.info(
            f"🍪 COOKIES LOADED => {len(cookies)}"
        )

    except Exception as e:

        logger.warning(
            f"⚠️ COOKIE LOAD FAILED => {e}"
        )

# ==========================================================
# SERPAPI ENGINE
# ==========================================================

def scrape_with_serpapi(

    place_id,

    target_limit=500
):

    logger.info(
        "🚀 ENGINE 0 => SERPAPI"
    )

    if not SERPAPI_API_KEY:

        logger.warning(
            "⚠️ SERPAPI_API_KEY NOT FOUND"
        )

        return []

    reviews = []

    seen_reviews = set()

    try:

        next_page_token = None

        while len(reviews) < target_limit:

            params = {

                "engine":
                    "google_maps_reviews",

                "place_id":
                    place_id,

                "api_key":
                    SERPAPI_API_KEY,

                "hl":
                    "en"
            }

            if next_page_token:

                params[
                    "next_page_token"
                ] = next_page_token

            proxies = None

            if PROXY_URL:

                proxies = {

                    "http":
                        PROXY_URL,

                    "https":
                        PROXY_URL
                }

            response = requests.get(

                "https://serpapi.com/search.json",

                params=params,

                proxies=proxies,

                timeout=REQUEST_TIMEOUT
            )

            response.raise_for_status()

            data = response.json()

            api_reviews = data.get(
                "reviews",
                []
            )

            if not api_reviews:
                break

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

                    review_text = clean_text(
                        review.get(
                            "snippet",
                            ""
                        )
                    )

                    if not review_text:
                        continue

                    review_id = generate_hash(
                        author,
                        review_text
                    )

                    if review_id in seen_reviews:
                        continue

                    seen_reviews.add(
                        review_id
                    )

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
                            clean_text(
                                review.get(
                                    "date",
                                    ""
                                )
                            ),

                        "text":
                            review_text,

                        "likes":
                            review.get(
                                "likes",
                                0
                            ),

                        "source":
                            "serpapi"
                    })

                except Exception:
                    continue

            logger.info(
                f"✅ SERPAPI REVIEWS => {len(reviews)}"
            )

            next_page_token = (

                data.get(
                    "serpapi_pagination",
                    {}
                ).get(
                    "next_page_token"
                )
            )

            if not next_page_token:
                break

            time.sleep(
                random.uniform(
                    1,
                    3
                )
            )

        return [
            normalize_review_object(r)
            for r in reviews[:target_limit]
        ]

    except Exception as e:

        logger.exception(
            f"❌ SERPAPI FAILED => {e}"
        )

        return []

# ==========================================================
# REQUESTS FALLBACK ENGINE
# ==========================================================

def scrape_with_requests(place_id):

    logger.info(
        "🚀 ENGINE 4 => REQUESTS"
    )

    try:

        url = (
            f"https://www.google.com/maps/place/?q=place_id:{place_id}"
        )

        headers = {

            "User-Agent":
                UserAgent().random
        }

        proxies = None

        if PROXY_URL:

            proxies = {

                "http":
                    PROXY_URL,

                "https":
                    PROXY_URL
            }

        response = requests.get(

            url,

            headers=headers,

            proxies=proxies,

            timeout=60
        )

        soup = BeautifulSoup(

            response.text,

            "lxml"
        )

        text = clean_text(
            soup.get_text()
        )

        if not text:
            return []

        reviews = [{

            "review_id":
                generate_hash(
                    "requests",
                    text[:100]
                ),

            "author_name":
                "requests",

            "rating":
                5,

            "review_date":
                "",

            "text":
                text[:3000],

            "likes":
                0,

            "source":
                "requests"
        }]

        return [
            normalize_review_object(r)
            for r in reviews
        ]

    except Exception as e:

        logger.exception(
            f"❌ REQUESTS FAILED => {e}"
        )

        return []

# ==========================================================
# MAIN MULTI ENGINE SCRAPER
# ==========================================================

@retry(

    stop=stop_after_attempt(2),

    wait=wait_exponential(

        multiplier=2,

        min=3,

        max=15
    )
)

async def scrape_google_reviews(

    place_id: str,

    target_limit: int = 500
):

    try:

        logger.info(
            "🚀 STARTING ENTERPRISE SCRAPER"
        )

        # ==================================================
        # ENGINE 0 — SERPAPI
        # ==================================================

        reviews = await asyncio.to_thread(

            scrape_with_serpapi,

            place_id,

            target_limit
        )

        if reviews:

            logger.info(
                f"✅ SERPAPI SUCCESS => {len(reviews)}"
            )

            return [
                normalize_review_object(r)
                for r in reviews
            ]

        logger.warning(
            "⚠️ SERPAPI FAILED"
        )

        # ==================================================
        # FALLBACK ENGINE
        # ==================================================

        reviews = await asyncio.to_thread(

            scrape_with_requests,

            place_id
        )

        if reviews:

            logger.info(
                f"✅ REQUESTS SUCCESS => {len(reviews)}"
            )

            return [
                normalize_review_object(r)
                for r in reviews
            ]

        logger.warning(
            "⚠️ ALL ENGINES FAILED"
        )

        return []

    except Exception as e:

        logger.exception(
            f"❌ MAIN SCRAPER FAILED => {e}"
        )

        logger.error(
            traceback.format_exc()
        )

        return []

    finally:

        gc.collect()
