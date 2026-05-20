# ==========================================================
# FILE: app/services/scraper.py
# CAMOUFOX + GOOGLE REVIEWS SCRAPER
# ADVANCED STEALTH VERSION
# ==========================================================

import os
import re
import gc
import json
import time
import random
import asyncio
import hashlib
import logging
import traceback

from typing import Dict, Any, List

from fake_useragent import UserAgent

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential
)

from playwright.async_api import (
    TimeoutError
)

from camoufox.async_api import (
    AsyncCamoufox
)

# ==========================================================
# LOGGER
# ==========================================================

logger = logging.getLogger(
    "app.services.scraper"
)

# ==========================================================
# PROXY CONFIG
# ==========================================================

PROXY_SERVER = "http://gw.dataimpulse.com:823"

PROXY_USERNAME = "f24ab799ffcf42cf2c54"

PROXY_PASSWORD = "e25628cf2c1b3ba3"

# ==========================================================
# CONFIG
# ==========================================================

HEADLESS = True

MAX_SCROLLS = 150

MAX_IDLE_SCROLLS = 15

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

    text = text.replace("\t", " ")

    text = " ".join(text.split())

    return text[:5000]


def normalize_rating(value):

    try:

        match = re.search(
            r"([0-9.]+)",
            str(value)
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
# DETECT BLOCKING
# ==========================================================

async def detect_google_block(page):

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

                logger.warning(
                    f"⚠️ GOOGLE BLOCK DETECTED: {keyword}"
                )

                return True

        return False

    except Exception:

        return False

# ==========================================================
# HUMAN SCROLL
# ==========================================================

async def human_scroll(page):

    amount = random.randint(
        700,
        1500
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
# WARMUP SESSION
# ==========================================================

async def warmup_session(page):

    logger.info(
        "🔥 WARMING SESSION"
    )

    await page.goto(

        "https://www.google.com",

        wait_until="domcontentloaded",

        timeout=120000
    )

    await asyncio.sleep(8)

    await human_scroll(page)

    await asyncio.sleep(4)

# ==========================================================
# OPEN REVIEW PANEL
# ==========================================================

async def open_reviews_panel(page):

    logger.info(
        "📦 OPENING REVIEWS PANEL"
    )

    await asyncio.sleep(15)

    selectors = [

        'button[aria-label*="Reviews"]',

        'button[aria-label*="reviews"]',

        'button[data-value="Reviews"]',

        'div[role="tab"]',

        'button[jsaction]',

        'span',

        'button'
    ]

    for selector in selectors:

        try:

            elements = await page.query_selector_all(
                selector
            )

            logger.info(
                f"📦 ELEMENTS FOUND ({selector}): {len(elements)}"
            )

            for idx, element in enumerate(elements):

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
                        f"🔍 ELEMENT [{idx}]: {combined[:120]}"
                    )

                    keywords = [

                        "review",
                        "reviews",
                        "rating",
                        "ratings"
                    ]

                    matched = any(

                        keyword in combined

                        for keyword in keywords
                    )

                    if not matched:
                        continue

                    logger.info(
                        f"✅ REVIEW MATCHED: {combined}"
                    )

                    await element.scroll_into_view_if_needed()

                    await asyncio.sleep(3)

                    clicked = False

                    click_methods = [

                        lambda: element.click(
                            timeout=10000
                        ),

                        lambda: page.evaluate(
                            "(el) => el.click()",
                            element
                        )
                    ]

                    for method in click_methods:

                        try:

                            await method()

                            clicked = True

                            logger.info(
                                "✅ REVIEW BUTTON CLICKED"
                            )

                            break

                        except Exception:
                            continue

                    if not clicked:
                        continue

                    await asyncio.sleep(20)

                    await page.mouse.wheel(
                        0,
                        1500
                    )

                    await asyncio.sleep(8)

                    feed_selectors = [

                        'div[role="feed"]',

                        'div.m6QErb[aria-label]',

                        'div[class*="review"]',

                        'div.jftiEf',

                        'div[role="article"]'
                    ]

                    for feed_selector in feed_selectors:

                        try:

                            feed = await page.query_selector(
                                feed_selector
                            )

                            if feed:

                                logger.info(
                                    f"✅ REVIEW FEED VERIFIED: {feed_selector}"
                                )

                                return True

                        except Exception:
                            pass

                except Exception:
                    continue

        except Exception:
            continue

    logger.warning(
        "⚠️ REVIEWS BUTTON NOT FOUND"
    )

    html = await page.content()

    with open(

        "/tmp/review_debug.html",

        "w",

        encoding="utf-8"
    ) as f:

        f.write(html)

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

            for button in buttons:

                try:

                    await button.click()

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

    seen_ids = set()

    idle_scrolls = 0

    previous_count = 0

    for scroll in range(MAX_SCROLLS):

        logger.info(
            f"📦 SCROLL #{scroll}"
        )

        try:

            cards = await page.query_selector_all(

                'div[data-review-id], '
                'div.jftiEf, '
                'div[role="article"], '
                'div[class*="review"]'
            )

            logger.info(
                f"📦 REVIEW CARDS FOUND: {len(cards)}"
            )

            for card in cards:

                try:

                    author = ""
                    review_text = ""
                    rating = 5

                    author_selectors = [

                        '.d4r55',

                        '.TSUbDb',

                        'span[class*="d4r55"]'
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

                        '.MyEned',

                        'span[jscontroller]',

                        'span[class*="wiI7pd"]',

                        'div[class*="review"] span'
                    ]

                    for selector in text_selectors:

                        try:

                            elem = await card.query_selector(
                                selector
                            )

                            if elem:

                                review_text = clean_text(

                                    await elem.inner_text()
                                )

                                if review_text:
                                    break

                        except Exception:
                            pass

                    if not review_text:
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
                        review_text
                    )

                    if review_id in seen_ids:
                        continue

                    seen_ids.add(
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
                            review_text
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

            await expand_reviews(page)

            await human_scroll(page)

            current_count = len(reviews)

            if current_count == previous_count:

                idle_scrolls += 1

            else:

                idle_scrolls = 0

            previous_count = current_count

            if idle_scrolls >= MAX_IDLE_SCROLLS:

                logger.warning(
                    "⚠️ IDLE SCROLL LIMIT REACHED"
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

        proxy = {

            "server":
                PROXY_SERVER,

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

            geoip=True,

            block_webrtc=True,

            i_know_what_im_doing=True,

            proxy=proxy
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

            timeout=120000
        )

        proxy_info = await page.content()

        logger.info(
            f"🌐 PROXY INFO: {proxy_info[:500]}"
        )

        # ==================================================
        # WARMUP SESSION
        # ==================================================

        await warmup_session(page)

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

        await asyncio.sleep(20)

        blocked = await detect_google_block(
            page
        )

        if blocked:

            logger.warning(
                "⚠️ GOOGLE BLOCK DETECTED"
            )

            return []

        # ==================================================
        # CLICK BUSINESS
        # ==================================================

        logger.info(
            "📦 WAITING FOR BUSINESS RESULTS"
        )

        await asyncio.sleep(20)

        business_selectors = [

            'a.hfpxzc',

            'div[role="article"] a',

            'a[href*="/maps/place/"]',

            'div.Nv2PK a',

            'div.Nv2PK',

            'a[data-cid]',

            'a[data-value]'
        ]

        clicked = False

        for selector in business_selectors:

            try:

                logger.info(
                    f"🔍 TRYING BUSINESS SELECTOR: {selector}"
                )

                results = await page.query_selector_all(
                    selector
                )

                logger.info(
                    f"📦 RESULTS FOUND: {len(results)}"
                )

                if not results:
                    continue

                for idx, result in enumerate(results[:5]):

                    try:

                        text = safe_string(

                            await result.inner_text()
                        )

                        logger.info(
                            f"📦 RESULT [{idx}]: {text[:120]}"
                        )

                        await result.scroll_into_view_if_needed()

                        await asyncio.sleep(3)

                        click_success = False

                        click_methods = [

                            lambda: result.click(
                                timeout=10000
                            ),

                            lambda: page.evaluate(
                                "(el) => el.click()",
                                result
                            )
                        ]

                        for method in click_methods:

                            try:

                                await method()

                                click_success = True

                                break

                            except Exception:
                                continue

                        if not click_success:
                            continue

                        logger.info(
                            "✅ BUSINESS CLICKED"
                        )

                        clicked = True

                        await asyncio.sleep(20)

                        await page.mouse.wheel(
                            0,
                            1200
                        )

                        await asyncio.sleep(8)

                        break

                    except Exception:
                        continue

                if clicked:
                    break

            except Exception:
                continue

        if not clicked:

            logger.warning(
                "⚠️ BUSINESS CLICK FAILED"
            )

            html = await page.content()

            with open(

                "/tmp/business_debug.html",

                "w",

                encoding="utf-8"
            ) as f:

                f.write(html)

            return []

        # ==================================================
        # OPEN REVIEWS PANEL
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

                "/tmp/review_debug.html",

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

    except TimeoutError:

        logger.exception(
            "❌ PLAYWRIGHT TIMEOUT"
        )

        return []

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
