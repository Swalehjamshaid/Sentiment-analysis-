# ==========================================================
# CAMOUFOX + GOOGLE REVIEWS SCRAPER
# PROFESSIONAL STEALTH VERSION
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

from datetime import datetime
from typing import Dict, List, Any

from fake_useragent import UserAgent

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential
)

from playwright.async_api import async_playwright

from camoufox.async_api import AsyncCamoufox

# ==========================================================
# LOGGER
# ==========================================================

logger = logging.getLogger(
    "app.services.scraper"
)

# ==========================================================
# ENV VARIABLES
# ==========================================================

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

MAX_SCROLLS = 120

SCROLL_PAUSE_MIN = 2

SCROLL_PAUSE_MAX = 5

# ==========================================================
# HELPERS
# ==========================================================

def safe_string(value, default=""):

    try:

        if value is None:
            return default

        return str(value).strip()

    except Exception:

        return default


def clean_text(text):

    text = safe_string(text)

    text = text.replace("\n", " ")

    text = text.replace("\r", " ")

    text = " ".join(text.split())

    return text[:5000]


def normalize_rating(text):

    try:

        match = re.search(
            r"([0-9.]+)",
            str(text)
        )

        if match:

            return int(
                float(
                    match.group(1)
                )
            )

    except Exception:
        pass

    return 5


def generate_hash(author, text):

    raw = f"{author}_{text}"

    return hashlib.md5(
        raw.encode("utf-8")
    ).hexdigest()

# ==========================================================
# CAPTCHA DETECTION
# ==========================================================

async def detect_block(page):

    try:

        content = (
            await page.content()
        ).lower()

        keywords = [

            "captcha",

            "unusual traffic",

            "not a robot",

            "/sorry/"
        ]

        for keyword in keywords:

            if keyword in content:
                return True

        return False

    except Exception:
        return False

# ==========================================================
# HUMAN SCROLL
# ==========================================================

async def human_scroll(page):

    amount = random.randint(
        500,
        1200
    )

    await page.mouse.wheel(
        0,
        amount
    )

    await asyncio.sleep(

        random.uniform(
            SCROLL_PAUSE_MIN,
            SCROLL_PAUSE_MAX
        )
    )

# ==========================================================
# OPEN REVIEWS PANEL
# ==========================================================

async def open_reviews_panel(page):

    logger.info(
        "📦 OPENING REVIEWS PANEL"
    )

    await asyncio.sleep(10)

    selectors = [

        'button[aria-label*="Reviews"]',

        'button[aria-label*="reviews"]',

        'button[data-value="Reviews"]',

        'div[role="tab"]',

        'button[jsaction]'
    ]

    for selector in selectors:

        try:

            elements = await page.query_selector_all(
                selector
            )

            logger.info(
                f"📦 SELECTOR {selector} -> {len(elements)}"
            )

            for element in elements:

                try:

                    text = safe_string(
                        await element.inner_text()
                    ).lower()

                    aria = safe_string(

                        await element.get_attribute(
                            "aria-label"
                        )

                    ).lower()

                    combined = (
                        f"{text} {aria}"
                    ).lower()

                    logger.info(
                        f"🔍 ELEMENT: {combined[:120]}"
                    )

                    if (
                        "review" not in combined
                        and "rating" not in combined
                    ):
                        continue

                    await element.scroll_into_view_if_needed()

                    await asyncio.sleep(2)

                    try:

                        await element.click(
                            timeout=5000
                        )

                    except Exception:

                        try:

                            await page.evaluate(
                                """
                                (el) => el.click()
                                """,
                                element
                            )

                        except Exception:
                            continue

                    logger.info(
                        "✅ REVIEW BUTTON CLICKED"
                    )

                    await asyncio.sleep(8)

                    feed = await page.query_selector(
                        'div[role="feed"]'
                    )

                    if feed:

                        logger.info(
                            "✅ REVIEW FEED VERIFIED"
                        )

                        return True

                except Exception:
                    continue

        except Exception:
            continue

    logger.warning(
        "⚠️ REVIEW BUTTON NOT FOUND"
    )

    return False

# ==========================================================
# EXPAND REVIEWS
# ==========================================================

async def expand_reviews(page):

    selectors = [

        'button.w8nwRe',

        'button[jsaction*="expandReview"]'
    ]

    for selector in selectors:

        try:

            buttons = await page.query_selector_all(
                selector
            )

            for btn in buttons:

                try:

                    await btn.click()

                except Exception:
                    pass

        except Exception:
            pass

# ==========================================================
# EXTRACT REVIEWS
# ==========================================================

async def extract_reviews(

    page,

    target_limit=500
):

    logger.info(
        "📦 STARTING REVIEW EXTRACTION"
    )

    reviews = []

    seen = set()

    idle_scrolls = 0

    previous_count = 0

    for scroll in range(MAX_SCROLLS):

        logger.info(
            f"📦 SCROLL #{scroll}"
        )

        try:

            cards = await page.query_selector_all(

                'div[data-review-id], div.jftiEf'
            )

            logger.info(
                f"📦 CARDS FOUND: {len(cards)}"
            )

            for card in cards:

                try:

                    author = ""
                    text = ""
                    rating = 5

                    author_selectors = [

                        '.d4r55',

                        '.TSUbDb'
                    ]

                    for selector in author_selectors:

                        try:

                            elem = await card.query_selector(
                                selector
                            )

                            if elem:

                                author = clean_text(

                                    await elem.inner_text()
                                )

                                if author:
                                    break

                        except Exception:
                            pass

                    text_selectors = [

                        '.wiI7pd',

                        '.MyEned'
                    ]

                    for selector in text_selectors:

                        try:

                            elem = await card.query_selector(
                                selector
                            )

                            if elem:

                                text = clean_text(

                                    await elem.inner_text()
                                )

                                if text:
                                    break

                        except Exception:
                            pass

                    if not text:
                        continue

                    rating_selectors = [

                        'span[aria-label*="star"]',

                        'span.kvMYJc'
                    ]

                    for selector in rating_selectors:

                        try:

                            elem = await card.query_selector(
                                selector
                            )

                            if elem:

                                label = await elem.get_attribute(
                                    "aria-label"
                                )

                                rating = normalize_rating(
                                    label
                                )

                                break

                        except Exception:
                            pass

                    review_id = generate_hash(
                        author,
                        text
                    )

                    if review_id in seen:
                        continue

                    seen.add(
                        review_id
                    )

                    reviews.append({

                        "review_id":
                            review_id,

                        "author_name":
                            author,

                        "rating":
                            rating,

                        "text":
                            text
                    })

                except Exception:
                    continue

            logger.info(
                f"✅ TOTAL REVIEWS: {len(reviews)}"
            )

            if len(reviews) >= target_limit:

                logger.info(
                    "🎯 TARGET LIMIT REACHED"
                )

                break

            await expand_reviews(
                page
            )

            await human_scroll(
                page
            )

            current_count = len(
                reviews
            )

            if current_count == previous_count:

                idle_scrolls += 1

            else:

                idle_scrolls = 0

            previous_count = current_count

            if idle_scrolls >= 12:

                logger.warning(
                    "⚠️ IDLE SCROLL LIMIT"
                )

                break

        except Exception as e:

            logger.exception(
                f"❌ EXTRACTION FAILED: {e}"
            )

    gc.collect()

    return reviews

# ==========================================================
# MAIN SCRAPER
# ==========================================================

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(
        multiplier=2,
        min=3,
        max=20
    )
)
async def scrape_google_reviews(

    business_name: str,

    target_limit: int = 500
):

    browser = None

    try:

        proxy = None

        if (
            PROXY_SERVER
            and PROXY_USERNAME
            and PROXY_PASSWORD
        ):

            proxy = {

                "server":
                    f"http://{PROXY_SERVER}",

                "username":
                    PROXY_USERNAME,

                "password":
                    PROXY_PASSWORD
            }

        logger.info(
            "🚀 STARTING CAMOUFOX"
        )

        browser = await AsyncCamoufox(
            headless=HEADLESS,

            humanize=True,

            proxy=proxy,

            geoip=True,

            block_webrtc=True,

            i_know_what_im_doing=True
        ).start()

        context = await browser.new_context(

            locale="en-US",

            timezone_id="America/New_York",

            user_agent=UserAgent().random,

            viewport={

                "width": 1440,

                "height": 960
            }
        )

        page = await context.new_page()

        # ==================================================
        # VERIFY PROXY
        # ==================================================

        logger.info(
            "🌐 VERIFYING PROXY"
        )

        await page.goto(

            "https://ipinfo.io/json",

            wait_until="domcontentloaded",

            timeout=90000
        )

        proxy_info = await page.content()

        logger.info(
            f"🌐 PROXY INFO: {proxy_info[:500]}"
        )

        # ==================================================
        # WARMUP SESSION
        # ==================================================

        logger.info(
            "🔥 WARMING SESSION"
        )

        await page.goto(
            "https://www.google.com"
        )

        await asyncio.sleep(8)

        await human_scroll(
            page
        )

        # ==================================================
        # GOOGLE MAPS SEARCH
        # ==================================================

        query = business_name.replace(
            " ",
            "+"
        )

        maps_url = (
            f"https://www.google.com/maps/search/{query}"
        )

        logger.info(
            f"🌐 MAPS URL: {maps_url}"
        )

        await page.goto(

            maps_url,

            wait_until="domcontentloaded",

            timeout=120000
        )

        await asyncio.sleep(12)

        blocked = await detect_block(
            page
        )

        if blocked:

            logger.warning(
                "⚠️ GOOGLE BLOCK DETECTED"
            )

            return []

        # ==================================================
        # CLICK FIRST BUSINESS
        # ==================================================

        selectors = [

            'a.hfpxzc',

            'div[role="article"] a',

            'a[href*="/maps/place/"]'
        ]

        clicked = False

        for selector in selectors:

            try:

                results = await page.query_selector_all(
                    selector
                )

                logger.info(
                    f"📦 RESULTS FOUND: {len(results)}"
                )

                if not results:
                    continue

                first = results[0]

                await first.scroll_into_view_if_needed()

                await asyncio.sleep(3)

                await first.click()

                logger.info(
                    "✅ BUSINESS CLICKED"
                )

                clicked = True

                break

            except Exception:
                continue

        if not clicked:

            logger.warning(
                "⚠️ BUSINESS CLICK FAILED"
            )

            return []

        await asyncio.sleep(15)

        await human_scroll(
            page
        )

        # ==================================================
        # OPEN REVIEWS
        # ==================================================

        opened = await open_reviews_panel(
            page
        )

        if not opened:

            logger.warning(
                "⚠️ REVIEW PANEL FAILED"
            )

            html = await page.content()

            with open(

                "/tmp/google_debug.html",

                "w",

                encoding="utf-8"
            ) as f:

                f.write(html)

            return []

        # ==================================================
        # EXTRACT REVIEWS
        # ==================================================

        reviews = await extract_reviews(

            page,

            target_limit=target_limit
        )

        logger.info(
            f"✅ SCRAPED REVIEWS: {len(reviews)}"
        )

        return reviews

    except Exception as e:

        logger.exception(
            f"❌ SCRAPER FAILED: {e}"
        )

        logger.error(
            traceback.format_exc()
        )

        return []

    finally:

        try:

            if browser:

                await browser.close()

        except Exception:
            pass
