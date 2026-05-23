# ==========================================================
# FILE: app/services/scraper.py
# FINAL WORLD-CLASS SAFE HYBRID SCRAPER
# FULLY ALIGNED WITH:
# ✅ main.py
# ✅ reviews.py
# ✅ dashboard frontend
# ✅ Railway deployment
# ✅ Existing API routes
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

from datetime import (
    datetime,
    timedelta
)

# ==========================================================
# SAFE IMPORTS
# ==========================================================

try:
    import requests
except Exception:
    requests = None

try:
    from bs4 import BeautifulSoup
except Exception:
    BeautifulSoup = None

try:
    from fake_useragent import UserAgent
except Exception:
    UserAgent = None

try:
    from playwright.async_api import (
        async_playwright
    )
except Exception:
    async_playwright = None

try:
    from playwright_stealth import (
        stealth_async
    )
except Exception:
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

PLAYWRIGHT_TIMEOUT = 60000

HEADLESS = True

MAX_SCROLLS = 8

# ==========================================================
# ENGINE CHECK
# ==========================================================

def engine_available(engine):

    return engine is not None

# ==========================================================
# SAFE USER AGENT
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
        "Chrome/124.0 Safari/537.36"
    )

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

    return " ".join(text.split())[:5000]

# ==========================================================
# HASH REVIEW
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

        lower = review_date.lower()

        now = datetime.utcnow()

        if "day" in lower:

            num = int(
                re.search(
                    r"\d+",
                    lower
                ).group()
            )

            actual = (
                now - timedelta(days=num)
            )

        elif "week" in lower:

            num = int(
                re.search(
                    r"\d+",
                    lower
                ).group()
            )

            actual = (
                now - timedelta(days=num * 7)
            )

        elif "month" in lower:

            num = int(
                re.search(
                    r"\d+",
                    lower
                ).group()
            )

            actual = (
                now - timedelta(days=num * 30)
            )

        elif "year" in lower:

            num = int(
                re.search(
                    r"\d+",
                    lower
                ).group()
            )

            actual = (
                now - timedelta(days=num * 365)
            )

        else:

            actual = now

        return actual >= start_date

    except:

        return True

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
# HUMAN BEHAVIOR
# ==========================================================

async def human_behavior(page):

    try:

        for _ in range(random.randint(2, 5)):

            x = random.randint(100, 1400)

            y = random.randint(100, 900)

            await page.mouse.move(x, y)

            await asyncio.sleep(
                random.uniform(0.3, 1)
            )

    except:
        pass

# ==========================================================
# BLOCK DETECTION
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
# PLAYWRIGHT ENGINE
# ==========================================================

async def scrape_with_playwright(

    place_id,

    existing_ids=None,

    target_limit=40,

    start_date=None
):

    reviews = []

    existing_ids = existing_ids or set()

    if not engine_available(async_playwright):

        logger.warning(
            "⚠️ PLAYWRIGHT NOT AVAILABLE"
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

                    "--no-sandbox"
                ]
            )

            context = await browser.new_context(

                user_agent=get_user_agent(),

                locale="en-US",

                viewport={

                    "width": random.randint(1200, 1800),

                    "height": random.randint(800, 1400)
                }
            )

            page = await context.new_page()

            # ==================================================
            # STEALTH
            # ==================================================

            if engine_available(stealth_async):

                try:

                    await stealth_async(page)

                except Exception as stealth_error:

                    logger.warning(
                        f"⚠️ STEALTH FAILED => {stealth_error}"
                    )

            # ==================================================
            # URL
            # ==================================================

            url = (
                f"https://www.google.com/maps/place/?q=place_id:{place_id}"
            )

            logger.info(
                "🚀 PLAYWRIGHT STARTED"
            )

            await asyncio.wait_for(

                page.goto(

                    url,

                    wait_until="domcontentloaded",

                    timeout=PLAYWRIGHT_TIMEOUT
                ),

                timeout=70
            )

            if await detect_google_block(page):

                return []

            await human_behavior(page)

            await asyncio.sleep(3)

            # ==================================================
            # OPEN REVIEWS
            # ==================================================

            try:

                button = page.locator(
                    'button[jsaction*="pane.reviewChart.moreReviews"]'
                )

                if await button.count() > 0:

                    await button.first.click()

                    await asyncio.sleep(3)

            except:
                pass

            # ==================================================
            # SCROLL REVIEWS
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
                        random.uniform(1, 2)
                    )

                except:
                    pass

            # ==================================================
            # REVIEW CARDS
            # ==================================================

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

                    author = ""
                    text = ""
                    review_date = ""
                    rating = 5

                    try:

                        author = clean_text(
                            await card.locator(".d4r55").inner_text()
                        )

                    except:
                        pass

                    try:

                        text = clean_text(
                            await card.locator(".wiI7pd").inner_text()
                        )

                    except:
                        pass

                    if not text:
                        continue

                    try:

                        review_date = clean_text(
                            await card.locator(".rsqaWe").inner_text()
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
                f"✅ PLAYWRIGHT REVIEWS => {len(reviews)}"
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
# REQUESTS + BS4 ENGINE
# ==========================================================

def scrape_with_requests(place_id):

    try:

        if not engine_available(requests):

            logger.warning(
                "⚠️ REQUESTS NOT AVAILABLE"
            )

            return ""

        headers = {

            "User-Agent":
                get_user_agent()
        }

        response = requests.get(

            f"https://www.google.com/maps/place/?q=place_id:{place_id}",

            headers=headers,

            proxies=get_requests_proxy(),

            timeout=60
        )

        if not engine_available(BeautifulSoup):

            logger.warning(
                "⚠️ BS4 NOT AVAILABLE"
            )

            return ""

        soup = BeautifulSoup(
            response.text,
            "lxml"
        )

        logger.info(
            "✅ REQUESTS ENGINE SUCCESS"
        )

        return clean_text(
            soup.get_text()
        )

    except Exception as e:

        logger.warning(
            f"⚠️ REQUESTS ENGINE FAILED => {e}"
        )

        return ""

# ==========================================================
# SERPAPI ENGINE
# ==========================================================

def serpapi_true_next_reviews(

    place_id,

    existing_ids=None,

    target_limit=100,

    start_date=None
):

    logger.info(
        "🚀 SERPAPI FALLBACK STARTED"
    )

    reviews = []

    existing_ids = existing_ids or set()

    seen = set()

    try:

        if not engine_available(requests):

            logger.warning(
                "⚠️ REQUESTS DISABLED"
            )

            return []

        next_page_token = None

        total_new_reviews = 0

        max_pages = 20

        current_page = 0

        while (

            total_new_reviews < target_limit
            and
            current_page < max_pages
        ):

            current_page += 1

            logger.info(
                f"📄 SERPAPI PAGE => {current_page}"
            )

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

                    if review_id in seen:
                        continue

                    if review_id in existing_ids:
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

                        "text":
                            text,

                        "likes":
                            review.get(
                                "likes",
                                0
                            )
                    })

                    total_new_reviews += 1

                    if total_new_reviews >= target_limit:
                        break

                except:
                    continue

            if total_new_reviews >= target_limit:
                break

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

        logger.info(
            f"✅ SERPAPI REVIEWS => {len(reviews)}"
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

async def scrape_google_reviews(

    place_id,

    target_limit=100,

    start_date=None,

    end_date=None
):

    logger.info(
        "🚀 scrape_google_reviews STARTED"
    )

    try:

        existing_review_ids = set()

        # ==================================================
        # LAYER 1 — PLAYWRIGHT
        # ==================================================

        playwright_reviews = await scrape_with_playwright(

            place_id=place_id,

            existing_ids=existing_review_ids,

            target_limit=40,

            start_date=start_date
        )

        logger.info(
            f"✅ PLAYWRIGHT COUNT => {len(playwright_reviews)}"
        )

        # ==================================================
        # LAYER 2 — REQUESTS
        # ==================================================

        await asyncio.to_thread(

            scrape_with_requests,

            place_id
        )

        # ==================================================
        # LAYER 3 — SERPAPI FALLBACK
        # ==================================================

        remaining = (
            target_limit -
            len(playwright_reviews)
        )

        serp_reviews = []

        if remaining > 0:

            logger.info(
                f"🚀 SERPAPI FETCH => {remaining}"
            )

            serp_reviews = await asyncio.to_thread(

                serpapi_true_next_reviews,

                place_id,

                existing_review_ids,

                remaining,

                start_date
            )

        # ==================================================
        # FINAL MERGE
        # ==================================================

        final_reviews = []

        seen = set()

        for review in (

            playwright_reviews +

            serp_reviews
        ):

            review_id = review.get(
                "review_id"
            )

            if review_id in seen:
                continue

            seen.add(review_id)

            final_reviews.append(review)

        logger.info(
            f"✅ FINAL REVIEW COUNT => {len(final_reviews)}"
        )

        return (

            final_reviews

            if isinstance(
                final_reviews,
                list
            )

            else
            []
        )

    except Exception as e:

        logger.exception(
            f"❌ SCRAPER FAILED => {e}"
        )

        logger.error(
            traceback.format_exc()
        )

        return []

    finally:

        gc.collect()
