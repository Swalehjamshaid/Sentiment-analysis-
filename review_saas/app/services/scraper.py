# =========================================================
# FILE: app/services/scraper.py
# TRUSTLYTICS AI - WORLD CLASS ENTERPRISE SCRAPER
# HUMAN-LIKE • MULTI-LAYER • RESILIENT • FRONTEND SAFE
# =========================================================

from __future__ import annotations

print("🔥 SCRAPER.PY BOOTING")

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
import traceback
import logging

from datetime import datetime
from typing import (
    Dict,
    List,
    Any,
    Optional
)

print("✅ STANDARD LIBRARIES READY")

# =========================================================
# REQUESTS
# =========================================================

import requests

print("✅ REQUESTS READY")

# =========================================================
# CURL CFFI
# =========================================================

CURL_CFFI_AVAILABLE = False

try:

    from curl_cffi import requests as curl_requests

    CURL_CFFI_AVAILABLE = True

    print("✅ CURL_CFFI READY")

except Exception as e:

    print(f"❌ CURL_CFFI ERROR => {e}")

# =========================================================
# TENACITY
# =========================================================

from tenacity import (
    retry,
    stop_after_attempt,
    wait_random_exponential
)

print("✅ TENACITY READY")

# =========================================================
# BACKOFF
# =========================================================

import backoff

print("✅ BACKOFF READY")

# =========================================================
# BEAUTIFULSOUP
# =========================================================

BS4_AVAILABLE = False

try:

    from bs4 import BeautifulSoup

    BS4_AVAILABLE = True

    print("✅ BS4 READY")

except Exception as e:

    print(f"❌ BS4 ERROR => {e}")

# =========================================================
# SELECTOLAX
# =========================================================

SELECTOLAX_AVAILABLE = False

try:

    from selectolax.parser import HTMLParser

    SELECTOLAX_AVAILABLE = True

    print("✅ SELECTOLAX READY")

except Exception as e:

    print(f"❌ SELECTOLAX ERROR => {e}")

# =========================================================
# LXML
# =========================================================

LXML_AVAILABLE = False

try:

    from lxml import html

    LXML_AVAILABLE = True

    print("✅ LXML READY")

except Exception as e:

    print(f"❌ LXML ERROR => {e}")

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

    print("✅ PLAYWRIGHT READY")

except Exception as e:

    print(f"❌ PLAYWRIGHT ERROR => {e}")

# =========================================================
# PLAYWRIGHT STEALTH
# =========================================================

STEALTH_AVAILABLE = False

try:

    from playwright_stealth import stealth_async

    STEALTH_AVAILABLE = True

    print("✅ PLAYWRIGHT STEALTH READY")

except Exception as e:

    print(f"❌ STEALTH ERROR => {e}")

# =========================================================
# FAKE USER AGENT
# =========================================================

FAKE_UA_AVAILABLE = False

try:

    from fake_useragent import UserAgent

    fake_ua = UserAgent()

    FAKE_UA_AVAILABLE = True

    print("✅ FAKE USER AGENT READY")

except Exception as e:

    print(f"❌ FAKE USER AGENT ERROR => {e}")

    fake_ua = None

# =========================================================
# CRAWL4AI
# =========================================================

CRAWL4AI_AVAILABLE = False

try:

    from crawl4ai import AsyncWebCrawler

    CRAWL4AI_AVAILABLE = True

    print("✅ CRAWL4AI READY")

except Exception as e:

    print(f"❌ CRAWL4AI ERROR => {e}")

# =========================================================
# CACHE
# =========================================================

CACHE_AVAILABLE = False

try:

    from cachetools import TTLCache

    review_cache = TTLCache(
        maxsize=1000,
        ttl=3600
    )

    CACHE_AVAILABLE = True

    print("✅ CACHE READY")

except Exception as e:

    print(f"❌ CACHE ERROR => {e}")

# =========================================================
# LOGGER
# =========================================================

logger = logging.getLogger(__name__)

logger.setLevel(logging.INFO)

print("✅ LOGGER READY")

# =========================================================
# ENVIRONMENT VARIABLES
# =========================================================

SERPAPI_KEY = os.getenv(
    "SERPAPI_KEY",
    ""
).strip()

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

SCRAPER_TIMEOUT = int(
    os.getenv(
        "SCRAPER_TIMEOUT",
        "300"
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

print("✅ ENVIRONMENT VARIABLES READY")

# =========================================================
# PROXY POOL
# =========================================================

PROXY_POOL = []

if PROXY_SERVER:

    PROXY_POOL.append({

        "server":
            f"http://{PROXY_SERVER}",

        "username":
            PROXY_USERNAME,

        "password":
            PROXY_PASSWORD
    })

print(f"✅ PROXY POOL => {len(PROXY_POOL)}")

# =========================================================
# HELPERS
# =========================================================

def utc_now():

    return datetime.utcnow()

# =========================================================
# USER AGENT
# =========================================================

def get_user_agent():

    if FAKE_UA_AVAILABLE and fake_ua:

        try:

            return fake_ua.random

        except Exception:

            pass

    return (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/125.0 Safari/537.36"
    )

# =========================================================
# HUMAN DELAY
# =========================================================

async def human_delay(
    minimum=3,
    maximum=9
):

    await asyncio.sleep(
        random.uniform(
            minimum,
            maximum
        )
    )

# =========================================================
# FRONTEND SAFE RESPONSE
# =========================================================

def build_response(
    success: bool,
    reviews: Optional[List[Dict]] = None,
    provider_results: Optional[Dict] = None,
    errors: Optional[List[str]] = None
):

    reviews = reviews or []
    provider_results = provider_results or {}
    errors = errors or []

    return {

        "success":
            success,

        "reviews":
            reviews,

        "total_reviews":
            len(reviews),

        "provider_results":
            provider_results,

        "errors":
            errors,

        "timestamp":
            utc_now().isoformat()
    }

# =========================================================
# MAPS URL
# =========================================================

def maps_url(
    place_id: str
):

    return (
        "https://www.google.com/maps/place/"
        f"?q=place_id:{place_id}"
    )

# =========================================================
# REVIEW ID
# =========================================================

def generate_review_id(
    place_id: str,
    author: str,
    text: str
):

    raw = f"{place_id}_{author}_{text}"

    return hashlib.sha256(
        raw.encode()
    ).hexdigest()

# =========================================================
# NORMALIZER
# =========================================================

def normalize_review(
    review: Dict[str, Any],
    place_id: str
):

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
            "Anonymous"
        )

    ).strip()

    rating = review.get(
        "rating",
        5
    )

    try:

        rating = int(float(rating))

    except Exception:

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
            0.50,

        "google_review_time":
            utc_now(),

        "scraped_at":
            utc_now()
    }

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

        if review_id in seen:

            continue

        seen.add(review_id)

        unique_reviews.append(review)

    return unique_reviews

# =========================================================
# SERPAPI PROVIDER
# =========================================================

@retry(
    stop=stop_after_attempt(5),
    wait=wait_random_exponential(
        min=2,
        max=20
    ),
    reraise=True
)
def serpapi_reviews(
    place_id: str
):

    print("🔥 SERPAPI STARTED")

    reviews = []

    if not SERPAPI_KEY:

        print("❌ SERPAPI KEY MISSING")

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

        print(
            f"🔥 SERPAPI STATUS => {response.status_code}"
        )

        data = response.json()

        raw_reviews = data.get(
            "reviews",
            []
        )

        print(
            f"🔥 SERPAPI RAW => {len(raw_reviews)}"
        )

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

                reviews.append(normalized)

    except Exception as e:

        print(f"❌ SERPAPI ERROR => {e}")

    print(
        f"✅ SERPAPI REVIEWS => {len(reviews)}"
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

    print("🔥 PLAYWRIGHT STARTED")

    reviews = []

    if not PLAYWRIGHT_AVAILABLE:

        return reviews

    browser = None

    try:

        proxy = None

        if PROXY_POOL:

            proxy = random.choice(
                PROXY_POOL
            )

        async with async_playwright() as p:

            browser = await p.chromium.launch(

                headless=HEADLESS_MODE,

                proxy=proxy,

                args=[

                    "--disable-blink-features=AutomationControlled",

                    "--no-sandbox",

                    "--disable-setuid-sandbox",

                    "--disable-dev-shm-usage",

                    "--disable-gpu",

                    "--window-size=1920,1080"
                ]
            )

            print("✅ CHROMIUM STARTED")

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

                await stealth_async(page)

                print("✅ STEALTH ENABLED")

            await page.mouse.move(

                random.randint(100, 1200),

                random.randint(100, 700)
            )

            await human_delay()

            url = maps_url(
                place_id
            )

            print(
                f"🔥 TARGET URL => {url}"
            )

            await page.goto(

                url,

                wait_until="domcontentloaded",

                timeout=300000
            )

            await human_delay(
                5,
                10
            )

            review_selectors = [

                'button[jsaction*="pane.reviewChart.moreReviews"]',

                'button[aria-label*="reviews"]',

                'button[aria-label*="Reviews"]'
            ]

            clicked = False

            for selector in review_selectors:

                try:

                    button = page.locator(
                        selector
                    ).first

                    await button.click()

                    clicked = True

                    print(
                        f"✅ REVIEW BUTTON CLICKED => {selector}"
                    )

                    break

                except Exception:

                    continue

            await page.wait_for_timeout(
                10000
            )

            review_panel = page.locator(
                "div.m6QErb"
            ).nth(1)

            for _ in range(80):

                try:

                    await review_panel.hover()

                    await review_panel.evaluate(
                        "(el) => el.scrollTop = el.scrollHeight"
                    )

                    print(
                        "🖱️ HUMAN PANEL SCROLL"
                    )

                    await page.mouse.move(

                        random.randint(100, 1200),

                        random.randint(100, 700)
                    )

                    await human_delay(
                        4,
                        10
                    )

                except Exception as scroll_error:

                    print(
                        f"❌ SCROLL ERROR => {scroll_error}"
                    )

            html_content = await page.content()

            print(
                f"🔥 HTML LENGTH => {len(html_content)}"
            )

            # =================================================
            # BEAUTIFULSOUP
            # =================================================

            if BS4_AVAILABLE:

                soup = BeautifulSoup(
                    html_content,
                    "html.parser"
                )

                blocks = soup.select(
                    "div.jftiEf"
                )

                print(
                    f"🔥 BS4 BLOCKS => {len(blocks)}"
                )

                for block in blocks:

                    try:

                        author = "Anonymous"

                        rating = 5

                        text = ""

                        author_element = block.select_one(
                            ".d4r55"
                        )

                        if author_element:

                            author = author_element.text.strip()

                        text_element = block.select_one(
                            ".wiI7pd"
                        )

                        if text_element:

                            text = text_element.text.strip()

                        rating_element = block.select_one(
                            "span.kvMYJc"
                        )

                        if rating_element:

                            aria = rating_element.get(
                                "aria-label",
                                ""
                            )

                            match = re.search(
                                r"(\d)",
                                aria
                            )

                            if match:

                                rating = int(
                                    match.group(1)
                                )

                        review = normalize_review({

                            "author":
                                author,

                            "rating":
                                rating,

                            "review_text":
                                text

                        }, place_id)

                        if review:

                            reviews.append(review)

                    except Exception:

                        continue

            # =================================================
            # SELECTOLAX
            # =================================================

            if SELECTOLAX_AVAILABLE:

                tree = HTMLParser(
                    html_content
                )

                nodes = tree.css(
                    "div.jftiEf"
                )

                print(
                    f"🔥 SELECTOLAX BLOCKS => {len(nodes)}"
                )

            # =================================================
            # LXML
            # =================================================

            if LXML_AVAILABLE:

                tree = html.fromstring(
                    html_content
                )

                nodes = tree.xpath(
                    "//div[contains(@class,'jftiEf')]"
                )

                print(
                    f"🔥 LXML BLOCKS => {len(nodes)}"
                )

    except Exception as e:

        print(
            f"❌ PLAYWRIGHT ERROR => {e}"
        )

        print(
            traceback.format_exc()
        )

    finally:

        try:

            if browser:

                await browser.close()

                print("✅ BROWSER CLOSED")

        except Exception:

            pass

    print(
        f"✅ PLAYWRIGHT REVIEWS => {len(reviews)}"
    )

    return reviews

# =========================================================
# CRAWL4AI PROVIDER
# =========================================================

async def crawl4ai_reviews(
    place_id: str
):

    print("🔥 CRAWL4AI STARTED")

    reviews = []

    if not CRAWL4AI_AVAILABLE:

        return reviews

    try:

        async with AsyncWebCrawler() as crawler:

            result = await crawler.arun(
                url=maps_url(place_id)
            )

            print(
                f"🔥 CRAWL4AI RESULT => {result.success}"
            )

    except Exception as e:

        print(f"❌ CRAWL4AI ERROR => {e}")

    return reviews

# =========================================================
# MASTER SCRAPER
# =========================================================

async def scrape_google_reviews(
    place_id: str
):

    print(
        f"🔥 MASTER SCRAPER STARTED => {place_id}"
    )

    if not place_id:

        return build_response(

            success=False,

            reviews=[],

            errors=[
                "Invalid Place ID"
            ]
        )

    cache_key = f"reviews_{place_id}"

    if CACHE_AVAILABLE:

        cached = review_cache.get(
            cache_key
        )

        if cached:

            print("⚡ CACHE HIT")

            return cached

    all_reviews = []

    provider_results = {}

    errors = []

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
        ),

        (
            "crawl4ai",
            lambda: crawl4ai_reviews(
                place_id
            )
        )
    ]

    for provider_name, provider in providers:

        try:

            print(
                f"🔥 PROVIDER START => {provider_name}"
            )

            result = await provider()

            provider_results[
                provider_name
            ] = len(result)

            if result:

                all_reviews.extend(
                    result
                )

            print(
                f"✅ PROVIDER SUCCESS => {provider_name}"
            )

            print(
                f"🔥 TOTAL REVIEWS => {len(all_reviews)}"
            )

            if len(all_reviews) >= MAX_REVIEWS:

                break

        except Exception as provider_error:

            error_message = (
                f"{provider_name}: "
                f"{str(provider_error)}"
            )

            errors.append(
                error_message
            )

            print(
                f"❌ PROVIDER FAILED => {error_message}"
            )

    all_reviews = deduplicate_reviews(
        all_reviews
    )

    all_reviews = all_reviews[:MAX_REVIEWS]

    response = build_response(

        success=len(all_reviews) > 0,

        reviews=all_reviews,

        provider_results=provider_results,

        errors=errors
    )

    if CACHE_AVAILABLE:

        review_cache[
            cache_key
        ] = response

    print(
        f"✅ FINAL UNIQUE REVIEWS => {len(all_reviews)}"
    )

    return response

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
# FINAL READY
# =========================================================

print("✅ WORLD CLASS SCRAPER READY")
