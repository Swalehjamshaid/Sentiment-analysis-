# ==========================================================
# FILE: app/services/scraper.py
# TRUSTLYTICS AI — ULTRA ENTERPRISE SERPAPI SCRAPER
# MAY 2026 — FINAL PRODUCTION VERSION
#
# FEATURES:
# ✅ SERPAPI GOOGLE MAPS REVIEWS
# ✅ Playwright Stealth Backup
# ✅ DataImpulse Rotating Proxies
# ✅ PostgreSQL Existing Review Detection
# ✅ Incremental Sync
# ✅ Only NEW Review Extraction
# ✅ Async Optimized
# ✅ Railway Production Optimized
# ✅ Enterprise Logging
# ✅ Duplicate Protection
# ✅ Fast Extraction
# ✅ Human Simulation
# ✅ Google Block Protection
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
# DATABASE
# ==========================================================

from sqlalchemy import select

from app.core.db import AsyncSessionLocal

from app.core.models import Review

# ==========================================================
# OPTIONAL IMPORTS
# ==========================================================

try:
    import httpx
except:
    httpx = None

try:
    from playwright.async_api import (
        async_playwright
    )
except:
    async_playwright = None

try:
    from playwright_stealth import (
        stealth_async
    )
except:
    stealth_async = None

try:
    from fake_useragent import UserAgent
except:
    UserAgent = None

# ==========================================================
# LOGGER
# ==========================================================

logger = logging.getLogger(
    "app.services.scraper"
)

# ==========================================================
# ENV VARIABLES
# ==========================================================

SERPAPI_KEY = os.getenv(
    "SERPAPI_KEY"
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

MAX_SCROLLS = 20

HEADLESS = True

# ==========================================================
# HELPERS
# ==========================================================

def clean_text(text):

    try:

        if not text:
            return ""

        text = str(text)

        text = text.replace(
            "\n",
            " "
        )

        text = text.replace(
            "\r",
            " "
        )

        return " ".join(
            text.split()
        )[:5000]

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

        if UserAgent:

            return UserAgent().random

    except:
        pass

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

        number_match = re.search(
            r"(\d+)",
            text
        )

        number = (
            int(number_match.group(1))
            if number_match
            else 1
        )

        if "day" in text:

            return now - timedelta(
                days=number
            )

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

        return now

    except:

        return datetime.utcnow()

# ==========================================================

def get_proxy():

    try:

        if not PROXY_SERVER:

            return None

        session_id = hashlib.md5(

            str(time.time()).encode()

        ).hexdigest()[:12]

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
# LOAD EXISTING IDS
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
            f"⚠️ EXISTING IDS LOAD FAILED => {e}"
        )

        return set()

# ==========================================================
# SERPAPI SCRAPER
# ==========================================================

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

        async with httpx.AsyncClient(

            timeout=REQUEST_TIMEOUT

        ) as client:

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

            logger.info(
                f"🚀 SERPAPI STARTED => {place_id}"
            )

            response = await client.get(

                "https://serpapi.com/search.json",

                params=params
            )

            data = response.json()

            raw_reviews = data.get(
                "reviews",
                []
            )

            logger.info(
                f"📦 SERPAPI RAW => "
                f"{len(raw_reviews)}"
            )

            seen = set()

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

                    review_date = clean_text(
                        review.get(
                            "date",
                            ""
                        )
                    )

                    rating = int(

                        review.get(
                            "rating",
                            5
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
                            0
                    })

                    if len(reviews) >= target_limit:

                        break

                except:
                    continue

        logger.info(
            f"✅ SERPAPI REVIEWS => "
            f"{len(reviews)}"
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

async def playwright_backup(
    place_id,
    existing_ids=None,
    target_limit=50
):

    reviews = []

    existing_ids = existing_ids or set()

    if not async_playwright:

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

                    "--no-sandbox",

                    "--disable-gpu"
                ]
            )

            context = await browser.new_context(

                user_agent=get_user_agent(),

                locale="en-US"
            )

            page = await context.new_page()

            if stealth_async:

                await stealth_async(page)

            url = (
                f"https://www.google.com/maps/place/"
                f"?q=place_id:{place_id}"
            )

            logger.info(
                f"🚀 PLAYWRIGHT FALLBACK => {place_id}"
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

                    await asyncio.sleep(4)

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

                    await asyncio.sleep(1)

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
                            r"(\d)",
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
                            0
                    })

                    if len(reviews) >= target_limit:

                        break

                except:
                    continue

        logger.info(
            f"✅ PLAYWRIGHT REVIEWS => "
            f"{len(reviews)}"
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
    company_id: int,
    target_limit: int = 100,
    start_date=None,
    end_date=None
):

    logger.info(
        f"🚀 HYBRID SCRAPER STARTED => "
        f"{place_id}"
    )

    try:

        existing_review_ids = await load_existing_review_ids(
            company_id
        )

        # ==================================================
        # PRIMARY — SERPAPI
        # ==================================================

        serp_reviews = await scrape_serpapi_reviews(

            place_id=place_id,

            existing_ids=existing_review_ids,

            target_limit=target_limit
        )

        # ==================================================
        # FALLBACK — PLAYWRIGHT
        # ==================================================

        if len(serp_reviews) < 10:

            remaining = (
                target_limit
                -
                len(serp_reviews)
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
        # FINAL DEDUPE
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
