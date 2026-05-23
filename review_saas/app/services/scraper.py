# ==========================================================
# FILE: app/services/scraper.py
# ENTERPRISE HYBRID REVIEW ENGINE
# PLAYWRIGHT + REQUESTS + BS4 + SERPAPI FALLBACK
# FINAL STABLE VERSION
#
# LOGIC:
# 1. PLAYWRIGHT + PROXY
# 2. REQUESTS + BS4 + PROXY
# 3. STEALTH ROTATION
# 4. HUMAN BEHAVIOR
# 5. SERPAPI TRUE NEXT REVIEW ENGINE (FINAL FALLBACK)
#
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

REQUEST_TIMEOUT = 120

PLAYWRIGHT_TIMEOUT = 60000

HEADLESS = True

MAX_SCROLLS = 5

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
# LOAD EXISTING IDS
# ==========================================================

async def load_existing_review_ids(

    db,

    company_id
):

    try:

        query = """

        SELECT google_review_id
        FROM reviews
        WHERE company_id = :company_id

        """

        result = await db.execute(

            query,

            {

                "company_id":
                    company_id
            }
        )

        rows = result.fetchall()

        ids = {

            row[0]
            for row in rows
        }

        logger.info(
            f"✅ EXISTING IDS => {len(ids)}"
        )

        return ids

    except Exception as e:

        logger.warning(
            f"⚠️ LOAD IDS FAILED => {e}"
        )

        return set()

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
                random.uniform(0.3, 1)
            )

    except:
        pass

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
# PLAYWRIGHT ENGINE
# ==========================================================

@retry(

    stop=stop_after_attempt(3),

    wait=wait_exponential(

        multiplier=1,

        min=2,

        max=10
    ),

    reraise=True
)

async def scrape_with_playwright(

    place_id,

    existing_ids=None,

    target_limit=30,

    start_date=None
):

    reviews = []

    existing_ids = existing_ids or set()

    browser = None

    try:

        proxy = get_proxy()

        async with async_playwright() as p:

            browser = await p.chromium.launch(

                headless=HEADLESS,

                proxy=proxy,

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

                    "width": random.randint(1200, 1800),

                    "height": random.randint(800, 1400)
                }
            )

            page = await context.new_page()

            await stealth_async(page)

            url = (
                f"https://www.google.com/maps/place/?q=place_id:{place_id}"
            )

            await page.goto(

                url,

                wait_until="domcontentloaded",

                timeout=PLAYWRIGHT_TIMEOUT
            )

            if await detect_google_block(page):
                return []

            await human_behavior(page)

            try:

                button = page.locator(
                    'button[jsaction*="pane.reviewChart.moreReviews"]'
                )

                if await button.count() > 0:

                    await button.first.click()

                    await asyncio.sleep(2)

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

                    await asyncio.sleep(
                        random.uniform(0.5, 1)
                    )

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

                    author = ""
                    text = ""
                    review_date = ""

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
                            5,

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

            await context.close()

            await browser.close()

            logger.info(
                f"✅ PLAYWRIGHT REVIEWS => {len(reviews)}"
            )

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

def scrape_with_requests(

    place_id
):

    try:

        headers = {

            "User-Agent":
                UserAgent().random
        }

        response = requests.get(

            f"https://www.google.com/maps/place/?q=place_id:{place_id}",

            headers=headers,

            proxies=get_requests_proxy(),

            timeout=60
        )

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
# FINAL FALLBACK — SERPAPI TRUE NEXT ENGINE
# ==========================================================

def serpapi_true_next_reviews(

    place_id,

    existing_ids=None,

    target_limit=100,

    start_date=None
):

    logger.info(
        "🚀 FINAL FALLBACK => SERPAPI"
    )

    reviews = []

    seen = set()

    existing_ids = existing_ids or set()

    try:

        next_page_token = None

        true_new_reviews = 0

        while true_new_reviews < target_limit:

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

                    true_new_reviews += 1

                except:
                    continue

            logger.info(
                f"✅ SERPAPI TRUE NEW => {true_new_reviews}"
            )

            if true_new_reviews >= target_limit:
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
            f"✅ FINAL SERPAPI REVIEWS => {len(reviews)}"
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

    db,

    company_id,

    place_id,

    target_limit=100,

    start_date=None,

    end_date=None
):

    logger.info(
        "🚀 HYBRID SCRAPER STARTED"
    )

    try:

        existing_review_ids = await load_existing_review_ids(

            db=db,

            company_id=company_id
        )

        logger.info(
            f"✅ EXISTING REVIEWS => {len(existing_review_ids)}"
        )

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
        # LAYER 2 — REQUESTS ENGINE
        # ==================================================

        await asyncio.to_thread(

            scrape_with_requests,

            place_id
        )

        # ==================================================
        # LAYER 3 — SERPAPI FINAL FALLBACK
        # ==================================================

        remaining = target_limit - len(playwright_reviews)

        serp_reviews = []

        if remaining > 0:

            logger.info(
                f"🚀 SERPAPI FALLBACK FETCH => {remaining}"
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

        return final_reviews

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
