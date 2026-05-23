# ==========================================================
# FILE: app/services/scraper.py
# TRUSTLYTICS AI — ULTRA ENTERPRISE SCRAPER
# MAY 2026 — FINAL RAILWAY VERSION
#
# FEATURES
# ==========================================================
# ✅ PLAYWRIGHT + STEALTH
# ✅ DATAIMPULSE PROXY
# ✅ FAST BURST ENGINE
# ✅ 500 SMART ATTEMPTS
# ✅ CONCURRENT WORKERS
# ✅ HUMAN-LIKE BEHAVIOR
# ✅ DATE RANGE FILTERING
# ✅ REVIEW EXPANSION
# ✅ GOOGLE BLOCK DETECTION
# ✅ SERPAPI FALLBACK
# ✅ NEXT 100 NEW REVIEWS
# ✅ DUPLICATE PROTECTION
# ✅ ENTERPRISE LOGGING
# ✅ RAILWAY SAFE
# ==========================================================

import os
import re
import gc
import time
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

from bs4 import BeautifulSoup

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

HEADLESS = True

FAST_TIMEOUT = 18

MAX_SCROLLS = 8

CONCURRENT_WORKERS = 20

TOTAL_ATTEMPTS = 500

REQUEST_TIMEOUT = 120

MINIMUM_REVIEWS = 100

# ==========================================================
# PROXY
# ==========================================================

def get_proxy():

    try:

        if (
            PROXY_SERVER and
            PROXY_USERNAME and
            PROXY_PASSWORD
        ):

            logger.info(
                "✅ PROXY ENABLED"
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
                re.search(
                    r"\d+",
                    lower_date
                ).group()
            )

            actual_date = now - timedelta(days=num)

        elif "week" in lower_date:

            num = int(
                re.search(
                    r"\d+",
                    lower_date
                ).group()
            )

            actual_date = now - timedelta(days=num * 7)

        elif "month" in lower_date:

            num = int(
                re.search(
                    r"\d+",
                    lower_date
                ).group()
            )

            actual_date = now - timedelta(days=num * 30)

        elif "year" in lower_date:

            num = int(
                re.search(
                    r"\d+",
                    lower_date
                ).group()
            )

            actual_date = now - timedelta(days=num * 365)

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
                random.uniform(0.2, 0.8)
            )

    except:
        pass

# ==========================================================
# EXTRACT REVIEWS
# ==========================================================

async def extract_reviews_from_page(

    page,

    existing_ids=None,

    target_limit=100,

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

        # ==================================================
        # EXPAND REVIEWS
        # ==================================================

        try:

            buttons = page.locator(
                "button.w8nwRe"
            )

            count = await buttons.count()

            for i in range(count):

                try:
                    await buttons.nth(i).click()
                except:
                    pass

        except:
            pass

        cards = page.locator(
            "div.jftiEf"
        )

        card_count = await cards.count()

        logger.info(
            f"📦 CARDS FOUND => {card_count}"
        )

        for i in range(card_count):

            try:

                card = cards.nth(i)

                author = "Anonymous"

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

                # ==============================================
                # DUPLICATE PREVENTION
                # ==============================================

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
            f"✅ NEW REVIEWS => {len(reviews)}"
        )

        return reviews

    except Exception as e:

        logger.warning(
            f"⚠️ EXTRACTION FAILED => {e}"
        )

        return []

# ==========================================================
# PLAYWRIGHT SCRAPER
# ==========================================================

async def scrape_with_playwright(

    place_id,

    existing_ids=None,

    target_limit=25,

    start_date=None
):

    browser = None

    try:

        proxy = get_proxy()

        async with async_playwright() as p:

            browser = await p.chromium.launch(

                headless=HEADLESS,

                proxy=proxy,

                slow_mo=30,

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

                    "width": 1400,

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

                timeout=60000
            )

            await human_behavior(page)

            await asyncio.sleep(
                random.uniform(1, 3)
            )

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

                    newest_option = page.locator(
                        'div[role="menuitemradio"]'
                    )

                    if await newest_option.count() > 1:

                        await newest_option.nth(1).click()

                        await asyncio.sleep(2)

            except:
                pass

            # ==================================================
            # SCROLL
            # ==================================================

            review_feed = page.locator(
                'div[role="feed"]'
            )

            previous_count = 0

            same_count = 0

            for i in range(MAX_SCROLLS):

                try:

                    await review_feed.evaluate(
                        "(el) => el.scrollTop = el.scrollHeight"
                    )

                    await asyncio.sleep(
                        random.uniform(0.3, 1)
                    )

                    cards = await page.locator(
                        "div.jftiEf"
                    ).count()

                    logger.info(
                        f"📜 SCROLL => {i+1} | {cards}"
                    )

                    if cards == previous_count:

                        same_count += 1

                    else:

                        same_count = 0

                    previous_count = cards

                    if same_count >= 2:

                        logger.info(
                            "✅ ALL REVIEWS LOADED"
                        )

                        break

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
            f"⚠️ PLAYWRIGHT FAILED => {e}"
        )

        return []

    finally:

        try:
            if browser:
                await browser.close()
        except:
            pass

# ==========================================================
# FAST WORKER
# ==========================================================

async def fast_worker(

    worker_id,

    place_id,

    existing_ids=None,

    target_limit=25,

    start_date=None
):

    try:

        logger.info(
            f"⚡ WORKER => {worker_id}"
        )

        return await asyncio.wait_for(

            scrape_with_playwright(

                place_id=place_id,

                existing_ids=existing_ids,

                target_limit=target_limit,

                start_date=start_date
            ),

            timeout=FAST_TIMEOUT
        )

    except Exception as e:

        logger.warning(
            f"⚠️ WORKER FAILED => {worker_id} | {e}"
        )

        return []

# ==========================================================
# ULTRA BURST ENGINE
# ==========================================================

async def ultra_burst_scraper(

    place_id,

    existing_ids=None,

    target_limit=100,

    start_date=None
):

    logger.info(
        "🚀 ULTRA BURST STARTED"
    )

    all_reviews = []

    existing_ids = existing_ids or set()

    completed = 0

    while completed < TOTAL_ATTEMPTS:

        logger.info(
            f"⚡ WAVE => {completed}/{TOTAL_ATTEMPTS}"
        )

        tasks = []

        for i in range(CONCURRENT_WORKERS):

            task = fast_worker(

                worker_id=i,

                place_id=place_id,

                existing_ids=existing_ids,

                target_limit=25,

                start_date=start_date
            )

            tasks.append(task)

        results = await asyncio.gather(

            *tasks,

            return_exceptions=True
        )

        completed += CONCURRENT_WORKERS

        # ==================================================
        # MERGE REVIEWS
        # ==================================================

        for result in results:

            if isinstance(result, list):

                all_reviews.extend(result)

        unique_reviews = {

            r["review_id"]: r
            for r in all_reviews
        }

        all_reviews = list(
            unique_reviews.values()
        )

        existing_ids.update({

            r["review_id"]
            for r in all_reviews
        })

        logger.info(
            f"✅ UNIQUE => {len(all_reviews)}"
        )

        if len(all_reviews) >= target_limit:

            logger.info(
                "✅ TARGET REACHED"
            )

            return all_reviews[:target_limit]

        await asyncio.sleep(
            random.uniform(0.5, 2)
        )

    return all_reviews[:target_limit]

# ==========================================================
# SERPAPI
# ==========================================================

def scrape_with_serpapi(

    place_id,

    existing_ids=None,

    target_limit=100,

    start_date=None
):

    logger.info(
        "🚀 SERPAPI STARTED"
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
                    # SKIP EXISTING REVIEWS
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
# MAIN SCRAPER
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
        "🚀 ENTERPRISE SCRAPER STARTED"
    )

    existing_review_ids = (
        existing_review_ids or set()
    )

    try:

        # ==================================================
        # BURST ENGINE
        # ==================================================

        reviews = await ultra_burst_scraper(

            place_id=place_id,

            existing_ids=existing_review_ids,

            target_limit=target_limit,

            start_date=start_date
        )

        # ==================================================
        # SERPAPI FALLBACK
        # ==================================================

        if len(reviews) < target_limit:

            existing_ids = {

                r["review_id"]
                for r in reviews
            }

            serp_reviews = await asyncio.to_thread(

                scrape_with_serpapi,

                place_id,

                existing_ids,

                target_limit,

                start_date
            )

            reviews.extend(serp_reviews)

            reviews = list({

                r["review_id"]: r
                for r in reviews

            }.values())

        logger.info(
            f"✅ FINAL REVIEWS => {len(reviews)}"
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
