# =========================================================
# FILE: app/services/scraper.py
# QUANTUM ENTERPRISE GOOGLE REVIEW SCRAPER
# FULLY ALIGNED WITH review.py
# =========================================================

from __future__ import annotations

# =========================================================
# STANDARD LIBRARIES
# =========================================================

import os
import re
import time
import json
import random
import asyncio
import hashlib
import logging
import traceback
import secrets

from datetime import datetime

from typing import (
    Dict,
    List,
    Any
)

# =========================================================
# LOGGER
# =========================================================

logger = logging.getLogger(__name__)

logger.setLevel(logging.INFO)

print("🚀 QUANTUM ENTERPRISE SCRAPER BOOTING")

# =========================================================
# REQUESTS
# =========================================================

import requests

# =========================================================
# CACHE
# =========================================================

from cachetools import TTLCache

review_cache = TTLCache(
    maxsize=2000,
    ttl=3600
)

# =========================================================
# TENACITY
# =========================================================

from tenacity import (
    retry,
    stop_after_attempt,
    wait_random_exponential
)

# =========================================================
# BACKOFF
# =========================================================

import backoff

# =========================================================
# SELECTOLAX
# =========================================================

SELECTOLAX_AVAILABLE = False

try:

    from selectolax.parser import HTMLParser

    SELECTOLAX_AVAILABLE = True

    logger.info(
        "✅ SELECTOLAX READY"
    )

except Exception as e:

    logger.error(
        f"❌ SELECTOLAX ERROR => {e}"
    )

# =========================================================
# BEAUTIFULSOUP
# =========================================================

BS4_AVAILABLE = False

try:

    from bs4 import BeautifulSoup

    BS4_AVAILABLE = True

    logger.info(
        "✅ BS4 READY"
    )

except Exception as e:

    logger.error(
        f"❌ BS4 ERROR => {e}"
    )

# =========================================================
# CURL_CFFI
# =========================================================

CURL_CFFI_AVAILABLE = False

try:

    from curl_cffi import requests as curl_requests

    CURL_CFFI_AVAILABLE = True

    logger.info(
        "✅ CURL_CFFI READY"
    )

except Exception as e:

    logger.error(
        f"❌ CURL_CFFI ERROR => {e}"
    )

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

    logger.info(
        "✅ PLAYWRIGHT READY"
    )

except Exception as e:

    logger.error(
        f"❌ PLAYWRIGHT ERROR => {e}"
    )

# =========================================================
# PLAYWRIGHT STEALTH
# =========================================================

STEALTH_AVAILABLE = False

try:

    from playwright_stealth import stealth_async

    STEALTH_AVAILABLE = True

    logger.info(
        "✅ STEALTH READY"
    )

except Exception as e:

    logger.error(
        f"❌ STEALTH ERROR => {e}"
    )

# =========================================================
# CRAWL4AI
# =========================================================

CRAWL4AI_AVAILABLE = False

try:

    from crawl4ai import AsyncWebCrawler

    CRAWL4AI_AVAILABLE = True

    logger.info(
        "✅ CRAWL4AI READY"
    )

except Exception as e:

    logger.error(
        f"❌ CRAWL4AI ERROR => {e}"
    )

# =========================================================
# FAKE USERAGENT
# =========================================================

FAKE_UA_AVAILABLE = False

try:

    from fake_useragent import UserAgent

    fake_ua = UserAgent()

    FAKE_UA_AVAILABLE = True

except Exception:

    fake_ua = None

# =========================================================
# ENVIRONMENT VARIABLES
# =========================================================

SCRAPER_TIMEOUT = int(
    os.getenv(
        "SCRAPER_TIMEOUT",
        "180"
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

# =========================================================
# PROXY CONFIGURATION
# =========================================================

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

PROXY_POOL = []

FAILED_PROXIES = set()

PROXY_HEALTH = {}

if PROXY_SERVER:

    PROXY_POOL.append({

        "server":
            f"http://{PROXY_SERVER}",

        "username":
            PROXY_USERNAME,

        "password":
            PROXY_PASSWORD
    })

logger.info(
    f"✅ PROXY COUNT => {len(PROXY_POOL)}"
)

# =========================================================
# CONCURRENCY
# =========================================================

SCRAPER_SEMAPHORE = asyncio.Semaphore(2)

# =========================================================
# QUANTUM ENTROPY
# =========================================================

def quantum_entropy():

    return secrets.randbelow(
        1000000
    )

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

    static_agents = [

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

    if FAKE_UA_AVAILABLE and fake_ua:

        try:

            return fake_ua.random

        except Exception:
            pass

    return random.choice(
        static_agents
    )

# =========================================================
# PROXY INTELLIGENCE
# =========================================================

def score_proxy(
    proxy_server: str
):

    stats = PROXY_HEALTH.get(
        proxy_server,
        {
            "success": 1,
            "fail": 1
        }
    )

    return (
        stats["success"] /
        (
            stats["success"] +
            stats["fail"]
        )
    )


def update_proxy_score(
    proxy_server: str,
    success: bool
):

    if proxy_server not in PROXY_HEALTH:

        PROXY_HEALTH[proxy_server] = {

            "success": 1,
            "fail": 1
        }

    if success:

        PROXY_HEALTH[
            proxy_server
        ]["success"] += 1

    else:

        PROXY_HEALTH[
            proxy_server
        ]["fail"] += 1


def get_best_proxy():

    try:

        available = [

            p for p in PROXY_POOL
            if p["server"] not in FAILED_PROXIES
        ]

        if not available:

            return None

        scored = sorted(

            available,

            key=lambda p: score_proxy(
                p["server"]
            ),

            reverse=True
        )

        return scored[0]

    except Exception:

        return None

# =========================================================
# QUANTUM DELAY
# =========================================================

async def quantum_delay():

    entropy = quantum_entropy()

    delay = (
        (entropy % 3000) / 1000
    )

    await asyncio.sleep(
        max(1, delay)
    )

# =========================================================
# CAPTCHA DETECTION
# =========================================================

def detect_captcha(
    html: str
):

    lower = html.lower()

    patterns = [

        "captcha",
        "unusual traffic",
        "not a robot",
        "sorry"
    ]

    return any(
        p in lower
        for p in patterns
    )

# =========================================================
# REVIEW NORMALIZATION
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

        rating = max(
            1,
            min(rating, 5)
        )

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

    seen = set()

    unique = []

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

        unique.append(review)

    return unique

# =========================================================
# DEBUG HELPERS
# =========================================================

async def debug_page(
    page,
    stage: str
):

    try:

        logger.info(
            f"🔥 PAGE URL [{stage}] => {page.url}"
        )

        logger.info(
            f"🔥 PAGE TITLE [{stage}] => {await page.title()}"
        )

        await page.screenshot(

            path=f"debug_{stage}.png",

            full_page=True
        )

    except Exception as e:

        logger.error(
            f"❌ DEBUG ERROR => {e}"
        )

# =========================================================
# PLAYWRIGHT PROVIDER
# =========================================================

@backoff.on_exception(
    backoff.expo,
    Exception,
    max_time=300
)
async def playwright_reviews(
    place_id: str
):

    reviews = []

    if not PLAYWRIGHT_AVAILABLE:

        logger.error(
            "❌ PLAYWRIGHT NOT AVAILABLE"
        )

        return reviews

    async with SCRAPER_SEMAPHORE:

        browser = None

        for attempt in range(3):

            proxy = get_best_proxy()

            try:

                logger.info(
                    f"🔥 PLAYWRIGHT ATTEMPT => {attempt+1}"
                )

                logger.info(
                    f"🔥 ACTIVE PROXY => {proxy}"
                )

                async with async_playwright() as p:

                    browser = await p.chromium.launch(

                        headless=HEADLESS_MODE,

                        proxy=proxy,

                        args=[

                            "--disable-blink-features=AutomationControlled",

                            "--disable-dev-shm-usage",

                            "--disable-gpu",

                            "--window-size=1920,1080",

                            "--no-sandbox"
                        ]
                    )

                    context = await browser.new_context(

                        user_agent=get_user_agent(),

                        locale="en-US",

                        viewport={

                            "width":
                                random.randint(
                                    1280,
                                    1920
                                ),

                            "height":
                                random.randint(
                                    720,
                                    1080
                                )
                        }
                    )

                    page = await context.new_page()

                    if STEALTH_AVAILABLE:

                        try:

                            await stealth_async(page)

                        except Exception:
                            pass

                    target_url = maps_url(
                        place_id
                    )

                    logger.info(
                        f"🔥 TARGET URL => {target_url}"
                    )

                    await page.goto(

                        target_url,

                        wait_until="domcontentloaded",

                        timeout=120000
                    )

                    await quantum_delay()

                    await debug_page(
                        page,
                        "before_reviews"
                    )

                    # =====================================================
                    # OPEN REVIEW PANEL
                    # =====================================================

                    selectors = [

                        'button[jsaction*="pane.reviewChart.moreReviews"]',

                        'button[aria-label*="reviews"]',

                        'button[aria-label*="Reviews"]',

                        'button[data-tab-index="1"]'
                    ]

                    clicked = False

                    for selector in selectors:

                        try:

                            locator = page.locator(
                                selector
                            ).first

                            count = await locator.count()

                            logger.info(
                                f"🔥 SELECTOR {selector} => {count}"
                            )

                            if count > 0:

                                await locator.click()

                                clicked = True

                                logger.info(
                                    f"✅ CLICKED => {selector}"
                                )

                                break

                        except Exception as e:

                            logger.error(
                                f"❌ CLICK ERROR => {e}"
                            )

                    if not clicked:

                        logger.error(
                            "❌ REVIEW BUTTON NOT FOUND"
                        )

                    await page.wait_for_timeout(
                        8000
                    )

                    await debug_page(
                        page,
                        "after_reviews_click"
                    )

                    html = await page.content()

                    if detect_captcha(html):

                        logger.error(
                            "❌ CAPTCHA DETECTED"
                        )

                        return reviews

                    # =====================================================
                    # DYNAMIC SCROLL
                    # =====================================================

                    review_panel = page.locator(
                        "div.m6QErb"
                    ).nth(1)

                    previous_count = 0

                    no_growth = 0

                    while no_growth < 5:

                        try:

                            await review_panel.hover()

                            scroll_amount = random.randint(
                                800,
                                1800
                            )

                            await review_panel.evaluate(
                                f"(el) => el.scrollTop += {scroll_amount}"
                            )

                            await quantum_delay()

                            current_count = await page.locator(
                                "div.jftiEf"
                            ).count()

                            logger.info(
                                f"🔥 REVIEW COUNT => {current_count}"
                            )

                            if current_count == previous_count:

                                no_growth += 1

                            else:

                                no_growth = 0

                            previous_count = current_count

                            if current_count >= MAX_REVIEWS:

                                break

                        except Exception as e:

                            logger.error(
                                f"❌ SCROLL ERROR => {e}"
                            )

                            break

                    cards = page.locator(
                        "div.jftiEf"
                    )

                    total_cards = await cards.count()

                    logger.info(
                        f"🔥 FINAL CARD COUNT => {total_cards}"
                    )

                    total_cards = min(
                        total_cards,
                        MAX_REVIEWS
                    )

                    for index in range(total_cards):

                        try:

                            card = cards.nth(index)

                            author = "Anonymous"

                            text = ""

                            rating = 5

                            try:

                                author_locator = card.locator(
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

                                text_locator = card.locator(
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

                                rating_locator = card.locator(
                                    "span.kvMYJc"
                                )

                                if await rating_locator.count() > 0:

                                    aria = await rating_locator.get_attribute(
                                        "aria-label"
                                    )

                                    if aria:

                                        match = re.search(
                                            r"(\\d)",
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

                        except Exception as e:

                            logger.error(
                                f"❌ REVIEW PARSE ERROR => {e}"
                            )

                    logger.info(
                        f"✅ PLAYWRIGHT REVIEWS => {len(reviews)}"
                    )

                    if proxy:

                        update_proxy_score(
                            proxy["server"],
                            True
                        )

                    if reviews:

                        break

            except Exception as e:

                logger.error(
                    f"❌ PLAYWRIGHT ERROR => {e}"
                )

                logger.error(
                    traceback.format_exc()
                )

                if proxy:

                    update_proxy_score(
                        proxy["server"],
                        False
                    )

                await asyncio.sleep(
                    random.uniform(3, 8)
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
        f"🚀 MASTER SCRAPER => {place_id}"
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

    try:

        result = await asyncio.wait_for(

            playwright_reviews(
                place_id
            ),

            timeout=300
        )

        if isinstance(
            result,
            list
        ):

            all_reviews.extend(
                result
            )

    except Exception as e:

        logger.error(
            f"❌ SCRAPER ERROR => {e}"
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
    "✅ QUANTUM ENTERPRISE SCRAPER READY"
)
