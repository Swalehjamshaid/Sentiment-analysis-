# ==========================================================
# FILE: app/services/scraper.py
# PRODUCTION GOOGLE REVIEWS SCRAPER 2026
# PLAYWRIGHT + CAMOUFOX + RESIDENTIAL PROXY
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

from typing import List, Dict, Any

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential
)

from fake_useragent import UserAgent

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
# CONFIG
# ==========================================================

HEADLESS = True

MAX_SCROLLS = 120

MAX_IDLE_SCROLLS = 12

SCROLL_PAUSE_MIN = 2

SCROLL_PAUSE_MAX = 5

# ==========================================================
# PROXY
# ==========================================================

PROXY_SERVER = os.getenv(
    "PROXY_SERVER",
    "http://gw.dataimpulse.com:823"
)

PROXY_USERNAME = os.getenv(
    "PROXY_USERNAME"
)

PROXY_PASSWORD = os.getenv(
    "PROXY_PASSWORD"
)

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
# HUMAN SCROLL
# ==========================================================

async def human_scroll(page):

    amount = random.randint(
        1000,
        3000
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
# SAVE DEBUG FILES
# ==========================================================

async def save_debug_files(

    page,

    name="debug"
):

    try:

        screenshot_path = f"/tmp/{name}.png"

        html_path = f"/tmp/{name}.html"

        await page.screenshot(

            path=screenshot_path,

            full_page=True
        )

        html = await page.content()

        with open(

            html_path,

            "w",

            encoding="utf-8"
        ) as f:

            f.write(html)

        logger.info(
            f"📸 DEBUG FILES SAVED => {name}"
        )

        logger.info(
            f"🌐 PAGE TITLE => {await page.title()}"
        )

        logger.info(
            f"🌐 CURRENT URL => {page.url}"
        )

    except Exception as e:

        logger.exception(
            f"❌ DEBUG SAVE FAILED: {e}"
        )

# ==========================================================
# DETECT GOOGLE BLOCK
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

            "/sorry/",

            "automated queries",

            "detected unusual traffic"
        ]

        for keyword in keywords:

            if keyword in content:

                logger.warning(
                    f"⚠️ GOOGLE BLOCK DETECTED => {keyword}"
                )

                return True

        return False

    except Exception:

        return False

# ==========================================================
# HANDLE CONSENT
# ==========================================================

async def handle_google_consent(page):

    try:

        buttons = await page.query_selector_all(
            "button"
        )

        for button in buttons:

            try:

                text = clean_text(
                    await button.inner_text()
                ).lower()

                if any(
                    x in text
                    for x in [
                        "accept",
                        "i agree",
                        "accept all"
                    ]
                ):

                    await button.click()

                    logger.info(
                        "✅ GOOGLE CONSENT ACCEPTED"
                    )

                    await asyncio.sleep(5)

                    return

            except Exception:
                continue

    except Exception:
        pass

# ==========================================================
# OPEN REVIEWS PANEL
# ==========================================================

async def open_reviews_panel(page):

    logger.info(
        "📦 OPENING REVIEW PANEL"
    )

    await asyncio.sleep(10)

    selectors = [

        'button[jsaction*="pane.reviewChart.moreReviews"]',

        'button[aria-label*="reviews"]',

        'button[aria-label*="Reviews"]',

        'div[role="button"][aria-label*="reviews"]',

        'div[role="button"][aria-label*="Reviews"]'
    ]

    for selector in selectors:

        try:

            elements = await page.query_selector_all(
                selector
            )

            logger.info(
                f"📦 SELECTOR [{selector}] => {len(elements)}"
            )

            for element in elements:

                try:

                    await element.scroll_into_view_if_needed()

                    await asyncio.sleep(2)

                    await element.click(
                        timeout=15000
                    )

                    logger.info(
                        "✅ REVIEW BUTTON CLICKED"
                    )

                    await asyncio.sleep(12)

                    review_feed = await page.query_selector(
                        'div[role="feed"]'
                    )

                    if review_feed:

                        logger.info(
                            "✅ REVIEW FEED FOUND"
                        )

                        return True

                except Exception:
                    continue

        except Exception:
            continue

    logger.warning(
        "⚠️ REVIEW PANEL NOT OPENED"
    )

    return False

# ==========================================================
# EXPAND REVIEWS
# ==========================================================

async def expand_reviews(page):

    try:

        buttons = await page.query_selector_all(
            'button'
        )

        for button in buttons:

            try:

                text = clean_text(
                    await button.inner_text()
                ).lower()

                if any(
                    x in text
                    for x in [
                        "more",
                        "full review"
                    ]
                ):

                    await button.click()

                    await asyncio.sleep(1)

            except Exception:
                continue

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
        "📦 STARTING EXTRACTION"
    )

    reviews = []

    seen_ids = set()

    idle_scrolls = 0

    previous_count = 0

    review_feed = await page.query_selector(
        'div[role="feed"]'
    )

    if not review_feed:

        logger.warning(
            "⚠️ REVIEW FEED NOT FOUND"
        )

        return []

    for scroll in range(MAX_SCROLLS):

        logger.info(
            f"📦 SCROLL => {scroll}"
        )

        try:

            cards = await page.query_selector_all(

                'div[data-review-id], '

                'div.jftiEf, '

                'div.MyEned, '

                'div[role="article"]'
            )

            logger.info(
                f"📦 CARDS FOUND => {len(cards)}"
            )

            for card in cards:

                try:

                    author = ""

                    review_text = ""

                    rating = 5

                    # ======================================
                    # AUTHOR
                    # ======================================

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

                    # ======================================
                    # REVIEW TEXT
                    # ======================================

                    text_selectors = [

                        '.wiI7pd',

                        '.MyEned',

                        'span[jscontroller]',

                        'span[class*="wiI7pd"]'
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

                    # ======================================
                    # RATING
                    # ======================================

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
                f"✅ TOTAL REVIEWS => {len(reviews)}"
            )

            if len(reviews) >= target_limit:

                logger.info(
                    "🎯 TARGET LIMIT REACHED"
                )

                break

            await expand_reviews(page)

            await page.evaluate("""

                () => {

                    const feed = document.querySelector(
                        'div[role="feed"]'
                    );

                    if (feed) {

                        feed.scrollBy(
                            0,
                            3000
                        );
                    }
                }

            """)

            await asyncio.sleep(

                random.uniform(4, 7)
            )

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
                f"❌ EXTRACTION ERROR => {e}"
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

    place_id: str,

    target_limit: int = 500
):

    browser = None

    try:

        logger.info(
            "🚀 STARTING GOOGLE SCRAPER"
        )

        proxy = {

            "server":
                PROXY_SERVER,

            "username":
                PROXY_USERNAME,

            "password":
                PROXY_PASSWORD
        }

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
        # ANTI-DETECTION
        # ==================================================

        await page.add_init_script("""

            Object.defineProperty(
                navigator,
                'webdriver',
                {
                    get: () => undefined
                }
            );

        """)

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

        logger.info(
            f"🌐 ACTIVE PROXY IP => {await page.text_content('body')}"
        )

        # ==================================================
        # GOOGLE WARMUP
        # ==================================================

        await page.goto(

            "https://www.google.com",

            wait_until="domcontentloaded",

            timeout=120000
        )

        await asyncio.sleep(8)

        await handle_google_consent(page)

        await human_scroll(page)

        # ==================================================
        # OPEN GOOGLE MAPS
        # ==================================================

        maps_url = (
            f"https://www.google.com/maps/place/?q=place_id:{place_id}"
        )

        logger.info(
            f"🌐 OPENING MAPS => {maps_url}"
        )

        await page.goto(

            maps_url,

            wait_until="domcontentloaded",

            timeout=120000
        )

        await asyncio.sleep(15)

        await handle_google_consent(page)

        await save_debug_files(
            page,
            "maps_loaded"
        )

        # ==================================================
        # DETECT BLOCK
        # ==================================================

        blocked = await detect_google_block(
            page
        )

        if blocked:

            logger.warning(
                "⚠️ GOOGLE BLOCKED REQUEST"
            )

            await save_debug_files(
                page,
                "google_blocked"
            )

            return []

        # ==================================================
        # OPEN REVIEWS
        # ==================================================

        opened = await open_reviews_panel(
            page
        )

        if not opened:

            logger.warning(
                "⚠️ REVIEWS PANEL FAILED"
            )

            await save_debug_files(
                page,
                "review_panel_failed"
            )

            return []

        # ==================================================
        # EXTRACTION
        # ==================================================

        reviews = await extract_reviews(

            page,

            target_limit=target_limit
        )

        # ==================================================
        # DEBUGGING
        # ==================================================

        logger.info(
            f"📦 PAGE LENGTH => {len(await page.content())}"
        )

        if len(reviews) == 0:

            logger.warning(
                "⚠️ NO REVIEWS SCRAPED"
            )

            await save_debug_files(
                page,
                "no_reviews_scraped"
            )

        else:

            logger.info(
                f"✅ SCRAPED REVIEWS => {len(reviews)}"
            )

            await save_debug_files(
                page,
                "reviews_success"
            )

        return reviews

    except TimeoutError:

        logger.exception(
            "❌ PLAYWRIGHT TIMEOUT"
        )

        return []

    except Exception as e:

        logger.exception(
            f"❌ SCRAPER FAILED => {e}"
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

        gc.collect()
