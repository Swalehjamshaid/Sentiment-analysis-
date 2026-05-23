# ==========================================================
# FILE: app/services/scraper.py
# TRUSTLYTICS AI — CONTINUOUS REVIEW INTELLIGENCE ENGINE
# MAY 2026 — ENTERPRISE ROTATION VERSION
#
# ARCHITECTURE
# ==========================================================
# 1. SERPAPI SEED ENGINE
#    → instantly uploads newest 100 reviews
#
# 2. BACKGROUND HARVESTER
#    → continuously harvests reviews
#
# 3. ROTATION ENGINE
#    → rotates proxies/fingerprints/user-agents
#
# 4. DUPLICATE ENGINE
#    → prevents old reviews
#
# 5. TEMPORAL ENGINE
#    → fetches reviews date-wise
#
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

from datetime import (
    datetime,
    timedelta
)

from fake_useragent import UserAgent

from bs4 import BeautifulSoup

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

# ==========================================================
# LOGGER
# ==========================================================

logger = logging.getLogger(
    "app.services.scraper"
)

# ==========================================================
# ENV
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

HEADLESS = True

FAST_TIMEOUT = 20

MAX_SCROLLS = 6

REQUEST_TIMEOUT = 120

BACKGROUND_SLEEP_MIN = 20

BACKGROUND_SLEEP_MAX = 60

# ==========================================================
# PROXY ROTATION
# ==========================================================

def get_proxy():

    try:

        session_id = random.randint(
            100000,
            999999
        )

        username = (
            f"{PROXY_USERNAME}-session-{session_id}"
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
# REQUESTS PROXY
# ==========================================================

def get_requests_proxy():

    try:

        session_id = random.randint(
            100000,
            999999
        )

        username = (
            f"{PROXY_USERNAME}-session-{session_id}"
        )

        proxy_url = (
            f"http://{username}:{PROXY_PASSWORD}@{PROXY_SERVER}"
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
# REVIEW HASH
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
# HUMAN BEHAVIOR
# ==========================================================

async def human_behavior(page):

    try:

        for _ in range(random.randint(1, 3)):

            x = random.randint(100, 1200)

            y = random.randint(100, 800)

            await page.mouse.move(x, y)

            await asyncio.sleep(
                random.uniform(0.2, 1)
            )

    except:
        pass

# ==========================================================
# EXTRACT REVIEWS
# ==========================================================

async def extract_reviews_from_page(

    page,

    existing_ids=None,

    target_limit=50,

    start_date=None,

    source="playwright"
):

    reviews = []

    seen = set()

    existing_ids = existing_ids or set()

    try:

        await page.wait_for_selector(
            "div.jftiEf",
            timeout=15000
        )

        cards = page.locator(
            "div.jftiEf"
        )

        count = await cards.count()

        logger.info(
            f"📦 CARDS => {count}"
        )

        for i in range(count):

            try:

                card = cards.nth(i)

                author = ""

                text = ""

                review_date = ""

                rating = 5

                try:

                    author = clean_text(
                        await card.locator(
                            ".d4r55"
                        ).inner_text()
                    )

                except:
                    pass

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

            except:
                continue

        logger.info(
            f"✅ EXTRACTED => {len(reviews)}"
        )

        return reviews

    except Exception as e:

        logger.warning(
            f"⚠️ EXTRACTION FAILED => {e}"
        )

        return []

# ==========================================================
# PLAYWRIGHT MICRO HARVESTER
# ==========================================================

async def micro_harvest(

    place_id,

    existing_ids=None,

    target_limit=20,

    start_date=None
):

    browser = None

    try:

        proxy = get_proxy()

        async with async_playwright() as p:

            browser = await p.chromium.launch(

                headless=HEADLESS,

                proxy=proxy,

                slow_mo=random.randint(20, 80),

                args=[

                    "--disable-blink-features=AutomationControlled",

                    "--disable-dev-shm-usage",

                    "--disable-gpu",

                    "--no-sandbox"
                ]
            )

            logger.info(
                "✅ BROWSER STARTED"
            )

            viewport_width = random.randint(
                1200,
                1800
            )

            viewport_height = random.randint(
                800,
                1400
            )

            context = await browser.new_context(

                user_agent=UserAgent().random,

                locale="en-US",

                viewport={

                    "width": viewport_width,

                    "height": viewport_height
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

            await page.goto(

                url,

                wait_until="domcontentloaded",

                timeout=60000
            )

            logger.info(
                "✅ PAGE LOADED"
            )

            if await detect_google_block(page):

                return []

            await human_behavior(page)

            # ==================================================
            # OPEN REVIEWS
            # ==================================================

            try:

                button = page.locator(
                    'button[jsaction*="pane.reviewChart.moreReviews"]'
                )

                if await button.count() > 0:

                    await button.first.click()

                    await asyncio.sleep(
                        random.uniform(1, 3)
                    )

            except:
                pass

            # ==================================================
            # SORT NEWEST
            # ==================================================

            try:

                sort_button = page.locator(
                    'button[aria-label*="Sort reviews"]'
                )

                if await sort_button.count() > 0:

                    await sort_button.first.click()

                    await asyncio.sleep(1)

                    newest = page.locator(
                        'div[role="menuitemradio"]'
                    )

                    if await newest.count() > 1:

                        await newest.nth(1).click()

                        await asyncio.sleep(2)

            except:
                pass

            # ==================================================
            # MICRO SCROLL
            # ==================================================

            review_feed = page.locator(
                'div[role="feed"]'
            )

            for i in range(MAX_SCROLLS):

                try:

                    await review_feed.evaluate(
                        "(el) => el.scrollTop = el.scrollHeight"
                    )

                    await asyncio.sleep(
                        random.uniform(0.3, 1)
                    )

                except:
                    pass

            reviews = await extract_reviews_from_page(

                page=page,

                existing_ids=existing_ids,

                target_limit=target_limit,

                start_date=start_date
            )

            await context.close()

            await browser.close()

            return reviews

    except Exception as e:

        logger.warning(
            f"⚠️ MICRO HARVEST FAILED => {e}"
        )

        return []

    finally:

        try:
            if browser:
                await browser.close()
        except:
            pass

# ==========================================================
# SERPAPI SEED ENGINE
# ==========================================================

def serpapi_seed_reviews(

    place_id,

    existing_ids=None,

    target_limit=100,

    start_date=None
):

    logger.info(
        "🚀 SERPAPI SEED STARTED"
    )

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

                    # ==========================================
                    # ONLY NEW REVIEWS
                    # ==========================================

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

                    if len(reviews) >= target_limit:
                        break

                except:
                    continue

            logger.info(
                f"✅ SERPAPI NEW => {len(reviews)}"
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

        return reviews

    except Exception as e:

        logger.warning(
            f"⚠️ SERPAPI FAILED => {e}"
        )

        return []

# ==========================================================
# CONTINUOUS BACKGROUND HARVESTER
# ==========================================================

async def continuous_background_harvester(

    place_id,

    existing_review_ids=None,

    start_date=None
):

    logger.info(
        "🚀 BACKGROUND HARVESTER STARTED"
    )

    existing_review_ids = (
        existing_review_ids or set()
    )

    while True:

        try:

            logger.info(
                "⚡ MICRO HARVEST CYCLE"
            )

            reviews = await asyncio.wait_for(

                micro_harvest(

                    place_id=place_id,

                    existing_ids=existing_review_ids,

                    target_limit=20,

                    start_date=start_date
                ),

                timeout=FAST_TIMEOUT
            )

            if reviews:

                logger.info(
                    f"✅ BACKGROUND NEW REVIEWS => {len(reviews)}"
                )

                existing_review_ids.update({

                    r["review_id"]
                    for r in reviews
                })

                # ==========================================
                # HERE SAVE TO DATABASE
                # ==========================================

                # save_reviews_to_database(reviews)

            sleep_time = random.randint(

                BACKGROUND_SLEEP_MIN,

                BACKGROUND_SLEEP_MAX
            )

            logger.info(
                f"😴 SLEEPING => {sleep_time}s"
            )

            await asyncio.sleep(
                sleep_time
            )

        except Exception as e:

            logger.warning(
                f"⚠️ BACKGROUND FAILED => {e}"
            )

            await asyncio.sleep(10)

# ==========================================================
# MAIN ENGINE
# ==========================================================

@retry(

    stop=stop_after_attempt(2),

    wait=wait_exponential(

        multiplier=2,

        min=2,

        max=8
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
        "🚀 REVIEW INTELLIGENCE ENGINE STARTED"
    )

    existing_review_ids = (
        existing_review_ids or set()
    )

    try:

        # ==================================================
        # 1. FAST SERPAPI SEED
        # ==================================================

        reviews = await asyncio.to_thread(

            serpapi_seed_reviews,

            place_id,

            existing_review_ids,

            target_limit,

            start_date
        )

        logger.info(
            f"✅ INITIAL REVIEWS => {len(reviews)}"
        )

        # ==================================================
        # 2. START BACKGROUND HARVESTER
        # ==================================================

        harvested_ids = {

            r["review_id"]
            for r in reviews
        }

        harvested_ids.update(
            existing_review_ids
        )

        asyncio.create_task(

            continuous_background_harvester(

                place_id=place_id,

                existing_review_ids=harvested_ids,

                start_date=start_date
            )
        )

        # ==================================================
        # 3. INSTANT FRONTEND RESPONSE
        # ==================================================

        return reviews[:target_limit]

    except Exception as e:

        logger.exception(
            f"❌ MAIN ENGINE FAILED => {e}"
        )

        logger.error(
            traceback.format_exc()
        )

        return []

    finally:

        gc.collect()
