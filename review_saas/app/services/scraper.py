# ==========================================================
# FILE: app/services/scraper.py
# TRUSTLYTICS AI — ENTERPRISE HYBRID SCRAPER
# FINAL PRODUCTION VERSION — MAY 2026
#
# FEATURES:
# ✅ Playwright Hybrid Scraping
# ✅ SERPAPI Fallback
# ✅ Duplicate Protection
# ✅ AI Ready
# ✅ Railway Optimized
# ✅ Proxy Ready
# ✅ Human Behavior Simulation
# ✅ Google Block Detection
# ✅ Enterprise Logging
# ✅ Database Compatible
# ✅ Frontend Compatible
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

from datetime import (
    datetime,
    timedelta
)

# ==========================================================
# OPTIONAL IMPORTS
# ==========================================================

try:
    import requests
except:
    requests = None

try:
    from bs4 import BeautifulSoup
except:
    BeautifulSoup = None

try:
    from fake_useragent import UserAgent
except:
    UserAgent = None

try:
    from playwright.async_api import async_playwright
except:
    async_playwright = None

try:
    from playwright_stealth import stealth_async
except:
    stealth_async = None

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

REQUEST_TIMEOUT = 120

PLAYWRIGHT_TIMEOUT = 70000

HEADLESS = True

MAX_SCROLLS = 15

PLAYWRIGHT_TARGET = 60

# ==========================================================
# HELPERS
# ==========================================================

def engine_available(engine):

    return engine is not None

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

def generate_hash(author, text):

    raw = f"{author}_{text}"

    return hashlib.md5(
        raw.encode("utf-8")
    ).hexdigest()

# ==========================================================

def get_user_agent():

    try:

        if UserAgent:

            return UserAgent().random

    except:
        pass

    return (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0 Safari/537.36"
    )

# ==========================================================

def parse_relative_date(relative_text):

    try:

        if not relative_text:
            return datetime.utcnow()

        text = relative_text.lower()

        now = datetime.utcnow()

        number_match = re.search(r"(\d+)", text)

        number = (
            int(number_match.group(1))
            if number_match
            else 1
        )

        if "day" in text:

            return now - timedelta(days=number)

        elif "week" in text:

            return now - timedelta(
                weeks=number
            )

        elif "month" in text:

            return now - timedelta(
                days=number * 30
            )

        elif "year" in text:

            return now - timedelta(
                days=number * 365
            )

        elif "hour" in text:

            return now - timedelta(
                hours=number
            )

        elif "minute" in text:

            return now - timedelta(
                minutes=number
            )

        return now

    except:

        return datetime.utcnow()

# ==========================================================

def passes_date_filter(
    review_date,
    start_date=None
):

    try:

        if not start_date:

            return True

        actual_date = parse_relative_date(
            review_date
        )

        return actual_date >= start_date

    except:

        return True

# ==========================================================

def get_proxy():

    try:

        if not PROXY_SERVER:
            return None

        session_id = random.randint(
            100000,
            999999
        )

        username = (
            f"{PROXY_USERNAME}"
            f"-session-{session_id}"
        )

        return {

            "server":
                f"http://{PROXY_SERVER}",

            "username":
                username,

            "password":
                PROXY_PASSWORD
        }

    except:

        return None

# ==========================================================

def get_requests_proxy():

    try:

        if not PROXY_SERVER:
            return None

        session_id = random.randint(
            100000,
            999999
        )

        username = (
            f"{PROXY_USERNAME}"
            f"-session-{session_id}"
        )

        proxy_url = (
            f"http://{username}:"
            f"{PROXY_PASSWORD}"
            f"@{PROXY_SERVER}"
        )

        return {

            "http": proxy_url,
            "https": proxy_url
        }

    except:

        return None

# ==========================================================

async def human_behavior(page):

    try:

        for _ in range(
            random.randint(2, 5)
        ):

            await page.mouse.move(

                random.randint(100, 1500),

                random.randint(100, 900)
            )

            await asyncio.sleep(

                random.uniform(0.5, 1.5)
            )

    except:
        pass

# ==========================================================

async def detect_google_block(page):

    try:

        content = (
            await page.content()
        ).lower()

        block_keywords = [

            "captcha",
            "unusual traffic",
            "automated queries",
            "/sorry/",
            "not a robot"
        ]

        for keyword in block_keywords:

            if keyword in content:

                logger.warning(
                    f"⚠️ GOOGLE BLOCK => {keyword}"
                )

                return True

        return False

    except:

        return False

# ==========================================================
# PLAYWRIGHT SCRAPER
# ==========================================================

async def scrape_with_playwright(
    place_id,
    existing_ids=None,
    target_limit=60,
    start_date=None
):

    reviews = []

    existing_ids = existing_ids or set()

    if not engine_available(async_playwright):

        logger.warning(
            "⚠️ Playwright unavailable"
        )

        return []

    browser = None

    try:

        async with async_playwright() as p:

            browser = await p.chromium.launch(

                headless=HEADLESS,

                proxy=get_proxy(),

                args=[

                    "--disable-blink-features=AutomationControlled",

                    "--disable-dev-shm-usage",

                    "--disable-gpu",

                    "--no-sandbox",

                    "--disable-setuid-sandbox"
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
                            800,
                            1080
                        )
                }
            )

            page = await context.new_page()

            if engine_available(stealth_async):

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

            if await detect_google_block(page):

                return []

            await human_behavior(page)

            await asyncio.sleep(4)

            # ==================================================
            # OPEN REVIEWS
            # ==================================================

            try:

                button = page.locator(
                    'button[jsaction*="pane.reviewChart.moreReviews"]'
                )

                if await button.count() > 0:

                    await button.first.click()

                    await asyncio.sleep(4)

            except:
                pass

            # ==================================================
            # SCROLL
            # ==================================================

            review_feed = page.locator(
                'div[role="feed"]'
            )

            for _ in range(MAX_SCROLLS):

                try:

                    await review_feed.evaluate(

                        "(el) => el.scrollTop = el.scrollHeight"
                    )

                    await asyncio.sleep(

                        random.uniform(
                            1.2,
                            2.8
                        )
                    )

                except:
                    pass

            # ==================================================
            # EXTRACT REVIEWS
            # ==================================================

            cards = page.locator(
                "div.jftiEf"
            )

            count = await cards.count()

            logger.info(
                f"📦 REVIEW CARDS => {count}"
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

                    if not passes_date_filter(
                        review_date,
                        start_date
                    ):
                        continue

                    # ==========================================
                    # RATING
                    # ==========================================

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

                    if (
                        review_id in seen
                        or
                        review_id in existing_ids
                    ):
                        continue

                    seen.add(review_id)

                    existing_ids.add(review_id)

                    review_data = {

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
                            0
                    }

                    reviews.append(
                        review_data
                    )

                    logger.info(
                        f"✅ REVIEW EXTRACTED => "
                        f"{author[:30]}"
                    )

                    if len(reviews) >= target_limit:

                        break

                except Exception as e:

                    logger.warning(
                        f"Card parse failed => {e}"
                    )

                    continue

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

        if browser:

            try:

                await browser.close()

            except:
                pass

# ==========================================================
# SERPAPI FALLBACK
# ==========================================================

def serpapi_reviews(
    place_id,
    existing_ids=None,
    target_limit=100,
    start_date=None
):

    reviews = []

    existing_ids = existing_ids or set()

    seen = set()

    if (
        not engine_available(requests)
        or
        not SERPAPI_API_KEY
    ):

        logger.warning(
            "⚠️ SERPAPI unavailable"
        )

        return reviews

    try:

        next_page_token = None

        total_new = 0

        while total_new < target_limit:

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

                timeout=REQUEST_TIMEOUT,

                proxies=get_requests_proxy()
            )

            response.raise_for_status()

            data = response.json()

            for review in data.get(
                "reviews",
                []
            ):

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

                    if (
                        review_id in seen
                        or
                        review_id in existing_ids
                    ):
                        continue

                    seen.add(review_id)

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

                        "google_review_time":
                            parse_relative_date(
                                review_date
                            ).isoformat(),

                        "text":
                            text,

                        "likes":
                            review.get(
                                "likes",
                                0
                            )
                    })

                    total_new += 1

                    if total_new >= target_limit:

                        break

                except:
                    continue

            next_page_token = data.get(
                "serpapi_pagination",
                {}
            ).get(
                "next_page_token"
            )

            if not next_page_token:

                break

            time.sleep(
                random.uniform(
                    1,
                    2.5
                )
            )

        logger.info(
            f"✅ SERPAPI REVIEWS => {len(reviews)}"
        )

        return reviews

    except Exception as e:

        logger.warning(
            f"⚠️ SERPAPI FAILED => {e}"
        )

        return reviews

# ==========================================================
# MAIN HYBRID SCRAPER
# ==========================================================

async def scrape_google_reviews(
    place_id: str,
    target_limit: int = 100,
    start_date=None,
    end_date=None
):

    logger.info(
        f"🚀 HYBRID SCRAPER STARTED => "
        f"{place_id}"
    )

    try:

        existing_review_ids = set()

        # ==================================================
        # PLAYWRIGHT LAYER
        # ==================================================

        playwright_reviews = await scrape_with_playwright(

            place_id=place_id,

            existing_ids=existing_review_ids,

            target_limit=min(
                PLAYWRIGHT_TARGET,
                target_limit
            ),

            start_date=start_date
        )

        # ==================================================
        # SERPAPI FALLBACK
        # ==================================================

        remaining = (
            target_limit
            -
            len(playwright_reviews)
        )

        serp_reviews = []

        if remaining > 0:

            logger.info(
                f"🚀 SERPAPI FALLBACK => "
                f"{remaining}"
            )

            serp_reviews = await asyncio.to_thread(

                serpapi_reviews,

                place_id,

                existing_review_ids,

                remaining,

                start_date
            )

        # ==================================================
        # MERGE + DEDUPLICATE
        # ==================================================

        final_reviews = []

        seen = set()

        for review in (
            playwright_reviews
            +
            serp_reviews
        ):

            rid = review.get(
                "review_id"
            )

            if rid and rid not in seen:

                seen.add(rid)

                final_reviews.append(review)

        logger.info(
            f"✅ FINAL REVIEW COUNT => "
            f"{len(final_reviews)}"
        )

        return final_reviews

    except Exception as e:

        logger.exception(
            f"❌ SCRAPER FAILED => {e}"
        )

        return []

    finally:

        gc.collect()
