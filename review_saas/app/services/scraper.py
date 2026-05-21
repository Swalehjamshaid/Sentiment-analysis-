# ==========================================================
# FILE: app/services/scraper.py
# CAMOUFOX + PLAYWRIGHT GOOGLE REVIEWS SCRAPER
# ADVANCED RAILWAY PRODUCTION VERSION
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

from typing import List, Dict, Any

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

logger.info(
    f"🌐 PROXY SERVER: {PROXY_SERVER}"
)

logger.info(
    f"🌐 USERNAME EXISTS: {bool(PROXY_USERNAME)}"
)

logger.info(
    f"🌐 PASSWORD EXISTS: {bool(PROXY_PASSWORD)}"
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
        600,
        1400
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

        logger.info(
            f"📸 SCREENSHOT SAVED: {screenshot_path}"
        )

        html = await page.content()

        with open(

            html_path,

            "w",

            encoding="utf-8"
        ) as f:

            f.write(html)

        logger.info(
            f"📄 HTML SAVED: {html_path}"
        )

        logger.info(
            f"🌐 PAGE TITLE: {await page.title()}"
        )

        logger.info(
            f"🌐 CURRENT URL: {page.url}"
        )

    except Exception as e:

        logger.exception(
            f"❌ DEBUG SAVE FAILED: {e}"
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
        "📦 ADVANCED REVIEW PANEL DETECTION STARTED"
    )

    await asyncio.sleep(12)

    try:

        # ==================================================
        # MASSIVE DOM WARMUP
        # ==================================================

        for _ in range(3):

            await page.mouse.wheel(0, 1200)

            await asyncio.sleep(3)

        # ==================================================
        # FIND ALL CLICKABLE ELEMENTS
        # ==================================================

        clickable_selectors = [

            "button",

            "span",

            "div",

            "a",

            '[role="button"]',

            '[role="tab"]'
        ]

        candidates = []

        for selector in clickable_selectors:

            try:

                elements = await page.query_selector_all(
                    selector
                )

                logger.info(
                    f"📦 FOUND {len(elements)} ELEMENTS FOR {selector}"
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

                        title = safe_string(

                            await element.get_attribute(
                                "title"
                            )
                        ).lower()

                        combined = (
                            f"{text} {aria} {title}"
                        ).lower()

                        if len(combined) < 3:
                            continue

                        score = 0

                        keywords = [

                            "review",
                            "reviews",
                            "rating",
                            "ratings",
                            "google reviews",
                            "customer reviews"
                        ]

                        for keyword in keywords:

                            if keyword in combined:
                                score += 10

                        if "5" in combined:
                            score += 2

                        if "star" in combined:
                            score += 3

                        if score <= 0:
                            continue

                        candidates.append({

                            "element": element,

                            "score": score,

                            "text": combined[:300]
                        })

                    except Exception:
                        continue

            except Exception:
                continue

        # ==================================================
        # SORT BEST CANDIDATES
        # ==================================================

        candidates = sorted(

            candidates,

            key=lambda x: x["score"],

            reverse=True
        )

        logger.info(
            f"📦 REVIEW CANDIDATES: {len(candidates)}"
        )

        # ==================================================
        # TRY CLICKING BEST CANDIDATES
        # ==================================================

        for idx, candidate in enumerate(candidates[:25]):

            try:

                logger.info(
                    f"🔍 TRYING CANDIDATE [{idx}] => {candidate['text']}"
                )

                element = candidate["element"]

                await element.scroll_into_view_if_needed()

                await asyncio.sleep(2)

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

                # ==============================================
                # WAIT FOR GOOGLE LAZY RENDER
                # ==============================================

                await asyncio.sleep(20)

                for _ in range(4):

                    await page.mouse.wheel(
                        0,
                        1800
                    )

                    await asyncio.sleep(4)

                # ==============================================
                # VERIFY REVIEW FEED
                # ==============================================

                feed_selectors = [

                    'div[role="feed"]',

                    'div[data-review-id]',

                    'div.jftiEf',

                    'div[role="article"]',

                    'div[class*="review"]',

                    'div[class*="jftiEf"]'
                ]

                for selector in feed_selectors:

                    try:

                        feed = await page.query_selector(
                            selector
                        )

                        if feed:

                            logger.info(
                                f"✅ REVIEW FEED VERIFIED: {selector}"
                            )

                            return True

                    except Exception:
                        pass

            except Exception:
                continue

        logger.warning(
            "⚠️ REVIEW BUTTON NOT FOUND"
        )

        await save_debug_files(
            page,
            "review_button_failed"
        )

        return False

    except Exception as e:

        logger.exception(
            f"❌ REVIEW PANEL ERROR: {e}"
        )

        return False
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

    
    place_id: str,

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

        await save_debug_files(
            page,
            "proxy_check"
        )

        # ==================================================
        # WARMUP SESSION
        # ==================================================

        await warmup_session(page)

        # ==================================================
        # OPEN GOOGLE MAPS PLACE
        # ==================================================

        maps_url = (
            f"https://www.google.com/maps/place/?q=place_id:{place_id}"
        )

        logger.info(
            f"🌐 Opening URL: {maps_url}"
        )

        await page.goto(

            maps_url,

            wait_until="domcontentloaded",

            timeout=120000
        )

        await asyncio.sleep(15)

        await save_debug_files(
            page,
            "maps_loaded"
        )

        blocked = await detect_google_block(
            page
        )

        if blocked:

            logger.warning(
                "⚠️ GOOGLE BLOCK DETECTED"
            )

            await save_debug_files(
                page,
                "google_blocked"
            )

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

            return []

        # ==================================================
        # EXTRACT REVIEWS
        # ==================================================

        reviews = await extract_reviews(

            page,

            target_limit=target_limit
        )
logger.info(
    f"📦 PAGE CONTENT LENGTH: {len(await page.content())}"
)

content = (await page.content()).lower()

keywords = [

    "review",

    "reviews",

    "rating",

    "ratings",

    "jftief",

    "data-review-id"
]

for keyword in keywords:

    logger.info(
        f"🔍 KEYWORD [{keyword}] EXISTS: {keyword in content}"
    )





if len(reviews) == 0:

    logger.warning(
        "⚠️ NO REVIEWS SCRAPED"
    )

    await save_debug_files(
        page,
        "no_reviews_scraped"
    )
        

        logger.info(
            f"✅ SCRAPED REVIEWS: {len(reviews)}"
        )

        await save_debug_files(
            page,
            "reviews_extracted"
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
