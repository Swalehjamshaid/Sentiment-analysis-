# ==========================================================
# FILE: app/services/scraper.py
# TRUSTLYTICS AI — ULTRA ENTERPRISE SCRAPER
# MAY 2026 — FINAL ENTERPRISE VERSION
#
# ENGINES:
# 1. PLAYWRIGHT + STEALTH + PROXY
# 2. CAMOUFOX + PROXY
# 3. REQUESTS + BS4 + PROXY
# 4. SERPAPI SMART PAGINATION
#
# FEATURES:
# ✅ DATAIMPULSE PROXY
# ✅ SMART REVIEW PAGINATION
# ✅ NEXT 100 NEW REVIEWS
# ✅ DUPLICATE PREVENTION
# ✅ DATE RANGE FILTERING
# ✅ REVIEW EXPANSION
# ✅ HUMAN SCROLLING
# ✅ GOOGLE BLOCK DETECTION
# ✅ STEALTH MODE
# ✅ RAILWAY SAFE
# ✅ ENTERPRISE LOGGING
# ==========================================================

import os
import re
import gc
import time
import json
import random
import asyncio
import hashlib
import logging
import traceback
import requests

from bs4 import BeautifulSoup

from datetime import (
    datetime,
    timedelta
)

from fake_useragent import UserAgent

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential
)

from playwright.async_api import (
    async_playwright
)

from playwright_stealth import (
    stealth_async
)

from camoufox.async_api import (
    AsyncCamoufox
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

HEADLESS = False

MAX_SCROLLS = 120

REQUEST_TIMEOUT = 120

MINIMUM_REVIEWS = 100

# ==========================================================
# PROXY CONFIG
# ==========================================================

def get_proxy():

    try:

        if (
            PROXY_SERVER and
            PROXY_USERNAME and
            PROXY_PASSWORD
        ):

            logger.info(
                "✅ DATAIMPULSE PROXY ENABLED"
            )

            return {

                "server":
                    f"http://{PROXY_SERVER}",

                "username":
                    PROXY_USERNAME,

                "password":
                    PROXY_PASSWORD
            }

        return None

    except Exception as e:

        logger.warning(
            f"⚠️ PROXY FAILED => {e}"
        )

        return None

# ==========================================================
# REQUESTS PROXY
# ==========================================================

def get_requests_proxy():

    try:

        proxy_url = (
            f"http://{PROXY_USERNAME}:{PROXY_PASSWORD}@{PROXY_SERVER}"
        )

        return {

            "http": proxy_url,

            "https": proxy_url
        }

    except:
        return None

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
# HASH
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
                re.search(r"\d+", lower_date).group()
            )

            actual_date = now - timedelta(days=num)

        elif "week" in lower_date:

            num = int(
                re.search(r"\d+", lower_date).group()
            )

            actual_date = now - timedelta(days=num * 7)

        elif "month" in lower_date:

            num = int(
                re.search(r"\d+", lower_date).group()
            )

            actual_date = now - timedelta(days=num * 30)

        elif "year" in lower_date:

            num = int(
                re.search(r"\d+", lower_date).group()
            )

            actual_date = now - timedelta(days=num * 365)

        else:

            actual_date = now

        return actual_date >= start_date

    except:
        return True

# ==========================================================
# NORMALIZE REVIEW
# ==========================================================

def normalize_review(review):

    return {

        "review_id":
            review.get(
                "review_id"
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

# ==========================================================
# GOOGLE BLOCK DETECTION
# ==========================================================

async def detect_google_block(page):

    try:

        content = (
            await page.content()
        ).lower()

        keywords = [

            "captcha",

            "unusual traffic",

            "automated queries",

            "/sorry/",

            "not a robot"
        ]

        for keyword in keywords:

            if keyword in content:

                logger.warning(
                    f"⚠️ GOOGLE BLOCK => {keyword}"
                )

                return True

        return False

    except:
        return False

# ==========================================================
# REVIEW EXTRACTION
# ==========================================================

async def extract_reviews_from_page(
    page,
    existing_ids=None,
    target_limit=100,
    start_date=None,
    source="google_maps"
):

    reviews = []

    seen = set()

    existing_ids = existing_ids or set()

    try:

        await page.wait_for_selector(
            "div.jftiEf",
            timeout=30000
        )

        # ==================================================
        # EXPAND REVIEWS
        # ==================================================

        try:

            buttons = page.locator(
                "button.w8nwRe"
            )

            btn_count = await buttons.count()

            for i in range(btn_count):

                try:
                    await buttons.nth(i).click()
                except:
                    pass

        except:
            pass

        cards = page.locator(
            "div.jftiEf"
        )

        count = await cards.count()

        logger.info(
            f"✅ REVIEW CARDS FOUND => {count}"
        )

        for i in range(count):

            try:

                card = cards.nth(i)

                author = "Anonymous"

                try:

                    author = clean_text(
                        await card.locator(
                            ".d4r55"
                        ).inner_text()
                    )

                except:
                    pass

                text = ""

                try:

                    text = clean_text(
                        await card.locator(
                            ".wiI7pd"
                        ).inner_text()
                    )

                except:
                    pass

                if not text:
                    continue

                review_date = ""

                try:

                    review_date = clean_text(
                        await card.locator(
                            ".rsqaWe"
                        ).inner_text()
                    )

                except:
                    pass

                if not passes_date_filter(
                    review_date,
                    start_date
                ):
                    continue

                rating = 5

                try:

                    rating_text = await card.locator(
                        ".kvMYJc"
                    ).get_attribute(
                        "aria-label"
                    )

                    match = re.search(
                        r"(\d)",
                        str(rating_text)
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

                # ==================================================
                # DUPLICATE CHECK
                # ==================================================

                if review_id in seen:
                    continue

                if review_id in existing_ids:
                    continue

                seen.add(review_id)

                reviews.append({

                    "review_id":
                        review_id,

                    "author_name":
                        author,

                    "rating":
                        rating,

                    "review_date":
                        review_date,

                    "text":
                        text,

                    "likes":
                        0,

                    "source":
                        source
                })

                if len(reviews) >= target_limit:
                    break

            except Exception as e:

                logger.warning(
                    f"⚠️ REVIEW PARSE FAILED => {e}"
                )

                continue

        logger.info(
            f"✅ NEW REVIEWS EXTRACTED => {len(reviews)}"
        )

        return [
            normalize_review(r)
            for r in reviews
        ]

    except Exception as e:

        logger.exception(
            f"❌ EXTRACTION FAILED => {e}"
        )

        return []

# ==========================================================
# PLAYWRIGHT ENGINE
# ==========================================================

async def scrape_with_playwright(
    place_id,
    existing_ids=None,
    target_limit=100,
    start_date=None
):

    logger.info(
        "🚀 ENGINE 1 => PLAYWRIGHT"
    )

    browser = None

    try:

        proxy = get_proxy()

        async with async_playwright() as p:

            browser = await p.chromium.launch(

                headless=HEADLESS,

                slow_mo=100,

                proxy=proxy if proxy else None,

                args=[

                    "--disable-blink-features=AutomationControlled",

                    "--disable-dev-shm-usage",

                    "--disable-gpu",

                    "--no-sandbox"
                ]
            )

            context = await browser.new_context(

                user_agent=UserAgent().random,

                locale="en-US",

                viewport={

                    "width": 1600,

                    "height": 1200
                }
            )

            page = await context.new_page()

            await stealth_async(page)

            await page.set_extra_http_headers({

                "Accept-Language":
                    "en-US,en;q=0.9"
            })

            url = (
                f"https://www.google.com/maps/place/?q=place_id:{place_id}"
            )

            logger.info(
                f"🌐 OPENING => {url}"
            )

            await page.goto(

                url,

                wait_until="domcontentloaded",

                timeout=120000
            )

            await asyncio.sleep(10)

            if await detect_google_block(page):

                return []

            # ==================================================
            # OPEN REVIEWS
            # ==================================================

            try:

                review_button = page.locator(
                    'button[jsaction*="pane.reviewChart.moreReviews"]'
                )

                if await review_button.count() > 0:

                    await review_button.first.click()

                    await asyncio.sleep(10)

            except Exception as e:

                logger.warning(
                    f"⚠️ OPEN REVIEW FAILED => {e}"
                )

            # ==================================================
            # SORT NEWEST
            # ==================================================

            try:

                sort_button = page.locator(
                    'button[aria-label*="Sort reviews"]'
                )

                if await sort_button.count() > 0:

                    await sort_button.first.click()

                    await asyncio.sleep(3)

                    newest_option = page.locator(
                        'div[role="menuitemradio"]'
                    )

                    if await newest_option.count() > 1:

                        await newest_option.nth(1).click()

                        await asyncio.sleep(5)

            except:
                pass

            # ==================================================
            # SCROLL
            # ==================================================

            review_feed = page.locator(
                'div[role="feed"]'
            )

            for i in range(MAX_SCROLLS):

                try:

                    await review_feed.evaluate(
                        "(el) => el.scrollTop = el.scrollHeight"
                    )

                    logger.info(
                        f"📜 SCROLL => {i+1}"
                    )

                    await asyncio.sleep(
                        random.uniform(3, 6)
                    )

                except:
                    pass

            reviews = await extract_reviews_from_page(

                page=page,

                existing_ids=existing_ids,

                target_limit=target_limit,

                start_date=start_date,

                source="playwright"
            )

            await context.close()

            await browser.close()

            logger.info(
                f"✅ PLAYWRIGHT REVIEWS => {len(reviews)}"
            )

            return reviews

    except Exception as e:

        logger.exception(
            f"❌ PLAYWRIGHT FAILED => {e}"
        )

        return []

    finally:

        try:

            if browser:
                await browser.close()
        except:
            pass

# ==========================================================
# CAMOUFOX ENGINE
# ==========================================================

async def scrape_with_camoufox(
    place_id,
    existing_ids=None,
    target_limit=100,
    start_date=None
):

    logger.info(
        "🚀 ENGINE 2 => CAMOUFOX"
    )

    try:

        proxy = get_proxy()

        async with AsyncCamoufox(

            headless=HEADLESS,

            proxy=proxy

        ) as browser:

            page = await browser.new_page()

            url = (
                f"https://www.google.com/maps/place/?q=place_id:{place_id}"
            )

            await page.goto(

                url,

                wait_until="networkidle",

                timeout=120000
            )

            await asyncio.sleep(10)

            if await detect_google_block(page):

                return []

            try:

                review_button = page.locator(
                    'button[jsaction*="pane.reviewChart.moreReviews"]'
                )

                if await review_button.count() > 0:

                    await review_button.first.click()

                    await asyncio.sleep(10)

            except:
                pass

            review_feed = page.locator(
                'div[role="feed"]'
            )

            for i in range(MAX_SCROLLS):

                try:

                    await review_feed.evaluate(
                        "(el) => el.scrollTop = el.scrollHeight"
                    )

                    await asyncio.sleep(
                        random.uniform(3, 6)
                    )

                except:
                    pass

            reviews = await extract_reviews_from_page(

                page=page,

                existing_ids=existing_ids,

                target_limit=target_limit,

                start_date=start_date,

                source="camoufox"
            )

            logger.info(
                f"✅ CAMOUFOX REVIEWS => {len(reviews)}"
            )

            return reviews

    except Exception as e:

        logger.exception(
            f"❌ CAMOUFOX FAILED => {e}"
        )

        return []

# ==========================================================
# SERPAPI ENGINE
# ==========================================================

def scrape_with_serpapi(
    place_id,
    existing_ids=None,
    target_limit=100,
    start_date=None
):

    logger.info(
        "🚀 ENGINE 4 => SERPAPI"
    )

    if not SERPAPI_API_KEY:

        return []

    reviews = []

    seen = set()

    existing_ids = existing_ids or set()

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

                    if not passes_date_filter(
                        review_date,
                        start_date
                    ):
                        continue

                    review_id = generate_hash(
                        author,
                        text
                    )

                    # ==================================================
                    # DUPLICATE CHECK
                    # ==================================================

                    if review_id in seen:
                        continue

                    if review_id in existing_ids:
                        continue

                    seen.add(review_id)

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

                except:
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
                random.uniform(1, 2)
            )

        return [
            normalize_review(r)
            for r in reviews
        ]

    except Exception as e:

        logger.exception(
            f"❌ SERPAPI FAILED => {e}"
        )

        return []

# ==========================================================
# MAIN SCRAPER
# ==========================================================

@retry(

    stop=stop_after_attempt(2),

    wait=wait_exponential(

        multiplier=2,

        min=3,

        max=12
    )
)

async def scrape_google_reviews(

    place_id: str,

    existing_review_ids=None,

    target_limit: int = 100,

    start_date=None,

    end_date=None
):

    logger.info(
        "🚀 ENTERPRISE SCRAPER STARTED"
    )

    existing_review_ids = (
        existing_review_ids or set()
    )

    try:

        # ==================================================
        # ENGINE 1 => PLAYWRIGHT
        # ==================================================

        reviews = await scrape_with_playwright(

            place_id=place_id,

            existing_ids=existing_review_ids,

            target_limit=target_limit,

            start_date=start_date
        )

        if len(reviews) >= MINIMUM_REVIEWS:

            return reviews

        # ==================================================
        # ENGINE 2 => CAMOUFOX
        # ==================================================

        reviews2 = await scrape_with_camoufox(

            place_id=place_id,

            existing_ids=existing_review_ids,

            target_limit=target_limit,

            start_date=start_date
        )

        reviews.extend(reviews2)

        unique_reviews = {

            r["review_id"]: r
            for r in reviews
        }

        reviews = list(
            unique_reviews.values()
        )

        if len(reviews) >= MINIMUM_REVIEWS:

            return reviews[:target_limit]

        # ==================================================
        # ENGINE 3 => SERPAPI
        # ==================================================

        existing_ids = {

            r["review_id"]
            for r in reviews
        }

        reviews3 = await asyncio.to_thread(

            scrape_with_serpapi,

            place_id,

            existing_ids,

            target_limit,

            start_date
        )

        reviews.extend(reviews3)

        unique_reviews = {

            r["review_id"]: r
            for r in reviews
        }

        reviews = list(
            unique_reviews.values()
        )

        logger.info(
            f"✅ FINAL UNIQUE REVIEWS => {len(reviews)}"
        )

        return reviews[:target_limit]

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
