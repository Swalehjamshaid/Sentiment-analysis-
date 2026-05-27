# =========================================================
# QUANTUM-INSPIRED ENTERPRISE SCRAPER ENGINE
# FILE: app/services/scraper.py
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
import math
import random
import asyncio
import hashlib
import logging
import traceback
import statistics
import secrets

from datetime import datetime

from typing import (
    Dict,
    List,
    Any,
    Optional
)

# =========================================================
# LOGGER
# =========================================================

logger = logging.getLogger(__name__)

logger.setLevel(logging.INFO)

print("🚀 QUANTUM SCRAPER ENGINE INITIALIZING")

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
# BS4
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
# FAKE USER AGENT
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

SCRAPINGDOG_API_KEY = os.getenv(
    "SCRAPINGDOG_API_KEY",
    ""
).strip()

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
# PROXY CONFIG
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
        ),

        (
            "Mozilla/5.0 "
            "(X11; Linux x86_64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/123.0 Safari/537.36"
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
# HUMAN ENTROPY
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

    except Exception:

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
# SCRAPINGDOG PROVIDER
# =========================================================

@retry(
    stop=stop_after_attempt(5),
    wait=wait_random_exponential(
        min=2,
        max=20
    ),
    reraise=True
)
def scrapingdog_reviews(
    place_id: str
):

    reviews = []

    if not SCRAPINGDOG_API_KEY:

        return reviews

    for attempt in range(5):

        try:

            logger.info(
                f"🔥 SCRAPINGDOG ATTEMPT => {attempt+1}"
            )

            response = requests.get(

                "https://api.scrapingdog.com/scrape",

                params={

                    "api_key":
                        SCRAPINGDOG_API_KEY,

                    "url":
                        maps_url(place_id),

                    "dynamic":
                        "true",

                    "country":
                        "us"
                },

                timeout=SCRAPER_TIMEOUT
            )

            if response.status_code != 200:

                continue

            html = response.text

            if detect_captcha(html):

                continue

            parser_results = []

            # =====================================================
            # QUANTUM PARALLEL PARSERS
            # =====================================================

            if SELECTOLAX_AVAILABLE:

                try:

                    tree = HTMLParser(html)

                    cards = tree.css(
                        "div.jftiEf"
                    )

                    for card in cards:

                        try:

                            author = ""
                            text = ""
                            rating = 5

                            author_node = card.css_first(
                                ".d4r55"
                            )

                            if author_node:

                                author = author_node.text()

                            text_node = card.css_first(
                                ".wiI7pd"
                            )

                            if text_node:

                                text = text_node.text()

                            normalized = normalize_review({

                                "author":
                                    author,

                                "rating":
                                    rating,

                                "review_text":
                                    text

                            }, place_id)

                            if normalized:

                                parser_results.append(
                                    normalized
                                )

                        except Exception:
                            continue

                except Exception:
                    pass

            if not parser_results and BS4_AVAILABLE:

                try:

                    soup = BeautifulSoup(
                        html,
                        "html.parser"
                    )

                    cards = soup.select(
                        "div.jftiEf"
                    )

                    for card in cards:

                        try:

                            author = ""
                            text = ""

                            author_node = card.select_one(
                                ".d4r55"
                            )

                            if author_node:

                                author = author_node.get_text(
                                    strip=True
                                )

                            text_node = card.select_one(
                                ".wiI7pd"
                            )

                            if text_node:

                                text = text_node.get_text(
                                    strip=True
                                )

                            normalized = normalize_review({

                                "author":
                                    author,

                                "rating":
                                    5,

                                "review_text":
                                    text

                            }, place_id)

                            if normalized:

                                parser_results.append(
                                    normalized
                                )

                        except Exception:
                            continue

                except Exception:
                    pass

            reviews.extend(
                parser_results
            )

            if reviews:

                break

        except Exception as e:

            logger.error(
                f"❌ SCRAPINGDOG ERROR => {e}"
            )

            time.sleep(
                random.uniform(2, 8)
            )

    return reviews

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
                    f"🔥 USING PROXY => {proxy}"
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

                    await page.goto(

                        maps_url(place_id),

                        wait_until="domcontentloaded",

                        timeout=120000
                    )

                    await quantum_delay()

                    selectors = [

                        'button[jsaction*="pane.reviewChart.moreReviews"]',

                        'button[aria-label*="reviews"]',

                        'button[aria-label*="Reviews"]'
                    ]

                    for selector in selectors:

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
                        5000
                    )

                    review_panel = page.locator(
                        "div.m6QErb"
                    ).nth(1)

                    previous_count = 0
                    no_growth = 0

                    while no_growth < 3:

                        try:

                            await review_panel.hover()

                            scroll_amount = random.randint(
                                800,
                                1800
                            )

                            await review_panel.evaluate(
                                f"(el) => el.scrollTop += {scroll_amount}"
                            )

                            await page.mouse.move(

                                random.randint(100, 1200),

                                random.randint(100, 700)
                            )

                            await quantum_delay()

                            current_count = await page.locator(
                                "div.jftiEf"
                            ).count()

                            if current_count == previous_count:

                                no_growth += 1

                            else:

                                no_growth = 0

                            previous_count = current_count

                            if current_count >= MAX_REVIEWS:

                                break

                        except Exception:
                            break

                    html = await page.content()

                    if detect_captcha(html):

                        raise Exception(
                            "CAPTCHA DETECTED"
                        )

                    cards = page.locator(
                        "div.jftiEf"
                    )

                    total_cards = await cards.count()

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
# QUANTUM PROVIDER ORCHESTRATOR
# =========================================================

async def scrape_google_reviews(
    place_id: str
):

    logger.info(
        f"🚀 QUANTUM SCRAPER => {place_id}"
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

    # =====================================================
    # QUANTUM PARALLEL EXECUTION
    # =====================================================

    tasks = [

        asyncio.to_thread(
            scrapingdog_reviews,
            place_id
        ),

        playwright_reviews(
            place_id
        )
    ]

    results = await asyncio.gather(

        *tasks,

        return_exceptions=True
    )

    all_reviews = []

    for result in results:

        if isinstance(
            result,
            Exception
        ):

            logger.error(
                f"❌ PROVIDER EXCEPTION => {result}"
            )

            continue

        if isinstance(
            result,
            list
        ):

            all_reviews.extend(
                result
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
