# app/services/scraper.py

```python
# ==========================================================
# FILE: app/services/scraper.py
# ENTERPRISE GOOGLE REVIEW SCRAPER - MAY 2026
# ==========================================================
# ENGINES:
# 0. SERPAPI
# 1. CAMOUFOX + PLAYWRIGHT
# 2. PLAYWRIGHT STEALTH
# 3. SELENIUMBASE UC
# 4. REQUESTS + BS4 FALLBACK
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

# ==========================================================
# RETRIES
# ==========================================================

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential
)

# ==========================================================
# USER AGENT
# ==========================================================

from fake_useragent import UserAgent

# ==========================================================
# PLAYWRIGHT
# ==========================================================

from playwright.async_api import (
    async_playwright,
    TimeoutError as PlaywrightTimeout
)

# ==========================================================
# CAMOUFOX
# ==========================================================

from camoufox.async_api import AsyncCamoufox

# ==========================================================
# PLAYWRIGHT STEALTH
# ==========================================================

from playwright_stealth import stealth_async

# ==========================================================
# SELENIUMBASE
# ==========================================================

from seleniumbase import SB

# ==========================================================
# REQUESTS / BS4
# ==========================================================

import requests

from bs4 import BeautifulSoup

# ==========================================================
# LOGGER
# ==========================================================

logger = logging.getLogger(
    "app.services.scraper"
)

# ==========================================================
# CONFIG
# ==========================================================

HEADLESS = False

MAX_SCROLLS = 120

MAX_IDLE_SCROLLS = 8

DEBUG_DIR = "/tmp"

COOKIES_FILE = "cookies.json"

REQUEST_TIMEOUT = 120

SERPAPI_API_KEY = os.getenv(
    "SERPAPI_API_KEY"
)

PROXY_URL = os.getenv(
    "PROXY_URL"
)

# ==========================================================
# HELPERS
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
# DEBUG FILES
# ==========================================================

async def save_debug_files(page, name):

    try:

        await page.screenshot(
            path=f"{DEBUG_DIR}/{name}.png",
            full_page=True
        )

        html = await page.content()

        with open(
            f"{DEBUG_DIR}/{name}.html",
            "w",
            encoding="utf-8"
        ) as f:

            f.write(html)

        logger.info(
            f"📸 DEBUG SAVED => {name}"
        )

    except Exception as e:

        logger.warning(
            f"⚠️ DEBUG SAVE FAILED => {e}"
        )

# ==========================================================
# CAPTCHA DETECTION
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
            "automated queries"
        ]

        for keyword in keywords:

            if keyword in content:

                logger.warning(
                    f"⚠️ GOOGLE BLOCK => {keyword}"
                )

                return True

        return False

    except Exception:

        return False

# ==========================================================
# HUMAN SCROLL
# ==========================================================

async def human_scroll(page):

    try:

        await page.mouse.wheel(
            0,
            random.randint(1500, 4000)
        )

        await asyncio.sleep(
            random.uniform(3, 7)
        )

    except Exception:
        pass

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
                        "✅ CONSENT ACCEPTED"
                    )

                    await asyncio.sleep(5)

                    return

            except Exception:
                continue

    except Exception:
        pass

# ==========================================================
# LOAD COOKIES
# ==========================================================

async def load_cookies(context):

    try:

        if not os.path.exists(
            COOKIES_FILE
        ):
            return

        with open(
            COOKIES_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            cookies = json.load(f)

        await context.add_cookies(
            cookies
        )

        logger.info(
            f"🍪 COOKIES LOADED => {len(cookies)}"
        )

    except Exception as e:

        logger.warning(
            f"⚠️ COOKIE LOAD FAILED => {e}"
        )

# ==========================================================
# OPEN REVIEW PANEL
# ==========================================================

async def open_reviews_panel(page):

    selectors = [
        'button[jsaction*="pane.reviewChart.moreReviews"]',
        'button[aria-label*="reviews"]',
        'button[aria-label*="Reviews"]',
        'div[role="button"][aria-label*="reviews"]',
        'xpath=//span[@class="z3HNkc"]/following-sibling::span//a'
    ]

    for selector in selectors:

        try:

            elements = await page.query_selector_all(
                selector
            )

            logger.info(
                f"📦 SELECTOR => {selector} => {len(elements)}"
            )

            for element in elements:

                try:

                    await element.scroll_into_view_if_needed()

                    await asyncio.sleep(2)

                    await element.click()

                    logger.info(
                        "✅ REVIEW BUTTON CLICKED"
                    )

                    await asyncio.sleep(10)

                    review_feed = await page.query_selector(
                        'div[role="feed"], div.RVCQse'
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

    return False

# ==========================================================
# EXPAND REVIEWS
# ==========================================================

async def expand_reviews(page):

    try:

        buttons = await page.query_selector_all(
            "button"
        )

        for button in buttons:

            try:

                text = clean_text(
                    await button.inner_text()
                ).lower()

                if "more" in text:

                    await button.click()

                    await asyncio.sleep(1)

            except Exception:
                continue

    except Exception:
        pass

# ==========================================================
# COMMON EXTRACTION ENGINE
# ==========================================================

async def extract_reviews_common(
    page,
    target_limit=500
):

    reviews = []

    seen_reviews = set()

    idle_scrolls = 0

    previous_count = 0

    review_feed = None

    for retry in range(5):

        review_feed = await page.query_selector(
            'div[role="feed"], div.RVCQse'
        )

        if review_feed:

            logger.info(
                "✅ REVIEW FEED FOUND"
            )

            break

        await human_scroll(page)

        await asyncio.sleep(
            random.uniform(3, 7)
        )

    if not review_feed:

        logger.warning(
            "⚠️ REVIEW FEED NOT FOUND"
        )

        await save_debug_files(
            page,
            "review_feed_missing"
        )

        return []

    for scroll in range(MAX_SCROLLS):

        logger.info(
            f"📦 SCROLL => {scroll}"
        )

        try:

            blocked = await detect_google_block(
                page
            )

            if blocked:

                await save_debug_files(
                    page,
                    "captcha_detected"
                )

                break

            review_modal = await page.query_selector(
                'div[role="dialog"]'
            )

            if not review_modal:

                logger.warning(
                    "⚠️ MODAL CLOSED"
                )

                reopened = await open_reviews_panel(
                    page
                )

                if reopened:

                    logger.info(
                        "✅ MODAL REOPENED"
                    )

                    await asyncio.sleep(10)

            try:

                await page.wait_for_selector(
                    'div[data-review-id], div[jsname="ShBeI"], div.jftiEf',
                    timeout=30000
                )

            except Exception:
                pass

            review_selectors = [
                'div[data-review-id]',
                'div[jsname="ShBeI"]',
                'div.jftiEf',
                'div.MyEned',
                'div[role="article"]'
            ]

            cards = []

            for selector in review_selectors:

                try:

                    selector_cards = await page.query_selector_all(
                        selector
                    )

                    logger.info(
                        f"📦 {selector} => {len(selector_cards)}"
                    )

                    cards.extend(selector_cards)

                except Exception:
                    continue

            unique_cards = []

            seen_elements = set()

            for card in cards:

                try:

                    html = await card.inner_html()

                    element_hash = hashlib.md5(
                        html.encode("utf-8")
                    ).hexdigest()

                    if element_hash in seen_elements:
                        continue

                    seen_elements.add(element_hash)

                    unique_cards.append(card)

                except Exception:
                    continue

            cards = unique_cards

            logger.info(
                f"📦 UNIQUE CARDS => {len(cards)}"
            )

            for card in cards:

                try:

                    author = ""

                    review_text = ""

                    rating = 5

                    review_date = ""

                    author_selectors = [
                        '.d4r55',
                        '.TSUbDb',
                        '.Vpc5Fe'
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
                            continue

                    text_selectors = [
                        '.wiI7pd',
                        '.MyEned',
                        '.OA1nbd',
                        'span[jscontroller]'
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
                            continue

                    if not review_text:
                        continue

                    rating_selectors = [
                        'span[aria-label*="star"]',
                        '.kvMYJc',
                        '.dHX2k'
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
                            continue

                    date_selectors = [
                        '.rsqaWe',
                        '.y3Ibjb'
                    ]

                    for selector in date_selectors:

                        try:

                            elem = await card.query_selector(
                                selector
                            )

                            if elem:

                                review_date = clean_text(
                                    await elem.inner_text()
                                )

                                if review_date:
                                    break

                        except Exception:
                            continue

                    review_id = generate_hash(
                        author,
                        review_text
                    )

                    if review_id in seen_reviews:
                        continue

                    seen_reviews.add(review_id)

                    reviews.append({
                        "review_id": review_id,
                        "author_name": author,
                        "rating": rating,
                        "review_date": review_date,
                        "text": review_text,
                        "source": "browser"
                    })

                except Exception:
                    continue

            logger.info(
                f"✅ TOTAL REVIEWS => {len(reviews)}"
            )

            if len(reviews) >= target_limit:
                break

            await expand_reviews(page)

            try:

                await page.evaluate(
                    """
                    () => {
                        const feed = document.querySelector(
                            'div[role="feed"], div.RVCQse'
                        );

                        if(feed){
                            feed.scrollBy(0, 4000);
                        }
                    }
                    """
                )

            except Exception:
                pass

            await human_scroll(page)

            current_count = len(reviews)

            if current_count == previous_count:

                idle_scrolls += 1

                logger.warning(
                    f"⚠️ IDLE => {idle_scrolls}"
                )

            else:

                idle_scrolls = 0

            previous_count = current_count

            if idle_scrolls >= 3:
                await open_reviews_panel(page)

            if idle_scrolls >= MAX_IDLE_SCROLLS:
                break

        except Exception as e:

            logger.exception(
                f"❌ EXTRACTION ERROR => {e}"
            )

            await save_debug_files(
                page,
                f"extract_error_{scroll}"
            )

    logger.info(
        f"✅ FINAL REVIEWS => {len(reviews)}"
    )

    return reviews

# ==========================================================
# ENGINE 0 - SERPAPI
# ==========================================================

def scrape_with_serpapi(
    place_id,
    target_limit=500
):

    logger.info(
        "🚀 ENGINE 0 => SERPAPI"
    )

    if not SERPAPI_API_KEY:

        logger.warning(
            "⚠️ SERPAPI_API_KEY NOT FOUND"
        )

        return []

    reviews = []

    seen_reviews = set()

    try:

        next_page_token = None

        while len(reviews) < target_limit:

            params = {
                "engine": "google_maps_reviews",
                "place_id": place_id,
                "api_key": SERPAPI_API_KEY,
                "hl": "en"
            }

            if next_page_token:
                params["next_page_token"] = next_page_token

            proxies = None

            if PROXY_URL:

                proxies = {
                    "http": PROXY_URL,
                    "https": PROXY_URL
                }

            response = requests.get(
                "https://serpapi.com/search.json",
                params=params,
                proxies=proxies,
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

                    review_text = clean_text(
                        review.get(
                            "snippet",
                            ""
                        )
                    )

                    if not review_text:
                        continue

                    review_id = generate_hash(
                        author,
                        review_text
                    )

                    if review_id in seen_reviews:
                        continue

                    seen_reviews.add(review_id)

                    reviews.append({
                        "review_id": review_id,
                        "author_name": author,
                        "rating": review.get("rating", 5),
                        "review_date": clean_text(review.get("date", "")),
                        "text": review_text,
                        "likes": review.get("likes", 0),
                        "source": "serpapi"
                    })

                except Exception:
                    continue

            logger.info(
                f"✅ SERPAPI REVIEWS => {len(reviews)}"
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
                random.uniform(1, 3)
            )

        return reviews[:target_limit]

    except Exception as e:

        logger.exception(
            f"❌ SERPAPI FAILED => {e}"
        )

        return []

# ==========================================================
# ENGINE 1 - CAMOUFOX
# ==========================================================

async def scrape_with_camoufox(
    place_id,
    target_limit
):

    logger.info(
        "🚀 ENGINE 1 => CAMOUFOX"
    )

    browser = None

    try:

        browser = await AsyncCamoufox(
            headless=HEADLESS,
            humanize=True,
            geoip=True,
            block_webrtc=True,
            i_know_what_im_doing=True
        ).start()

        context = await browser.new_context(
            user_agent=UserAgent().random,
            viewport={
                "width": 1440,
                "height": 960
            }
        )

        await load_cookies(context)

        page = await context.new_page()

        await stealth_async(page)

        await page.goto(
            f"https://www.google.com/maps/place/?q=place_id:{place_id}",
            wait_until="domcontentloaded",
            timeout=120000
        )

        await asyncio.sleep(15)

        await handle_google_consent(page)

        blocked = await detect_google_block(page)

        if blocked:
            return []

        opened = await open_reviews_panel(page)

        if not opened:
            return []

        reviews = await extract_reviews_common(
            page,
            target_limit
        )

        await save_debug_files(
            page,
            "camoufox_success"
        )

        return reviews

    except Exception as e:

        logger.exception(
            f"❌ CAMOUFOX FAILED => {e}"
        )

        return []

    finally:

        try:
            if browser:
                await browser.close()
        except Exception:
            pass

# ==========================================================
# ENGINE 2 - PLAYWRIGHT
# ==========================================================

async def scrape_with_playwright(
    place_id,
    target_limit
):

    logger.info(
        "🚀 ENGINE 2 => PLAYWRIGHT"
    )

    browser = None

    try:

        pw = await async_playwright().start()

        browser = await pw.chromium.launch(
            headless=HEADLESS
        )

        context = await browser.new_context(
            user_agent=UserAgent().random
        )

        await load_cookies(context)

        page = await context.new_page()

        await stealth_async(page)

        await page.goto(
            f"https://www.google.com/maps/place/?q=place_id:{place_id}",
            wait_until="domcontentloaded",
            timeout=120000
        )

        await asyncio.sleep(15)

        await handle_google_consent(page)

        opened = await open_reviews_panel(page)

        if not opened:
            return []

        reviews = await extract_reviews_common(
            page,
            target_limit
        )

        await save_debug_files(
            page,
            "playwright_success"
        )

        return reviews

    except Exception as e:

        logger.exception(
            f"❌ PLAYWRIGHT FAILED => {e}"
        )

        return []

    finally:

        try:
            if browser:
                await browser.close()
        except Exception:
            pass

# ==========================================================
# ENGINE 3 - SELENIUMBASE
# ==========================================================

def scrape_with_seleniumbase(
    place_id,
    target_limit
):

    logger.info(
        "🚀 ENGINE 3 => SELENIUMBASE"
    )

    reviews = []

    try:

        with SB(
            uc=True,
            headed=True
        ) as sb:

            url = (
                f"https://www.google.com/maps/place/?q=place_id:{place_id}"
            )

            sb.open(url)

            time.sleep(15)

            try:
                sb.click(
                    'button[jsaction*="pane.reviewChart.moreReviews"]'
                )
            except Exception:
                pass

            time.sleep(10)

            cards = sb.find_elements(
                'div[data-review-id]'
            )

            for card in cards:

                try:

                    text = clean_text(card.text)

                    if not text:
                        continue

                    review_id = generate_hash(
                        "selenium",
                        text
                    )

                    reviews.append({
                        "review_id": review_id,
                        "author_name": "selenium",
                        "rating": 5,
                        "text": text,
                        "source": "seleniumbase"
                    })

                except Exception:
                    continue

        return reviews

    except Exception as e:

        logger.exception(
            f"❌ SELENIUMBASE FAILED => {e}"
        )

        return []

# ==========================================================
# ENGINE 4 - REQUESTS FALLBACK
# ==========================================================

def scrape_with_requests(place_id):

    logger.info(
        "🚀 ENGINE 4 => REQUESTS"
    )

    try:

        url = (
            f"https://www.google.com/maps/place/?q=place_id:{place_id}"
        )

        headers = {
            "User-Agent": UserAgent().random
        }

        proxies = None

        if PROXY_URL:
            proxies = {
                "http": PROXY_URL,
                "https": PROXY_URL
            }

        response = requests.get(
            url,
            headers=headers,
            proxies=proxies,
            timeout=60
        )

        soup = BeautifulSoup(
            response.text,
            "lxml"
        )

        text = clean_text(
            soup.get_text()
        )

        if not text:
            return []

        return [{
            "review_id": generate_hash(
                "requests",
                text[:100]
            ),
            "author_name": "requests",
            "rating": 5,
            "text": text[:3000],
            "source": "requests"
        }]

    except Exception as e:

        logger.exception(
            f"❌ REQUESTS FAILED => {e}"
        )

        return []

# ==========================================================
# MAIN MULTI ENGINE SCRAPER
# ==========================================================

@retry(
    stop=stop_after_attempt(2),
    wait=wait_exponential(
        multiplier=2,
        min=3,
        max=15
    )
)
async def scrape_google_reviews(
    place_id: str,
    target_limit: int = 500
):

    try:

        logger.info(
            "🚀 STARTING ENTERPRISE SCRAPER"
        )

        reviews = await asyncio.to_thread(
            scrape_with_serpapi,
            place_id,
            target_limit
        )

        if reviews:

            logger.info(
                f"✅ SERPAPI SUCCESS => {len(reviews)}"
            )

            return reviews

        logger.warning(
            "⚠️ SERPAPI FAILED"
        )

        reviews = await scrape_with_camoufox(
            place_id,
            target_limit
        )

        if reviews:

            logger.info(
                f"✅ CAMOUFOX SUCCESS => {len(reviews)}"
            )

            return reviews

        logger.warning(
            "⚠️ CAMOUFOX FAILED"
        )

        reviews = await scrape_with_playwright(
            place_id,
            target_limit
        )

        if reviews:

            logger.info(
                f"✅ PLAYWRIGHT SUCCESS => {len(reviews)}"
            )

            return reviews

        logger.warning(
            "⚠️ PLAYWRIGHT FAILED"
        )

        reviews = await asyncio.to_thread(
            scrape_with_seleniumbase,
            place_id,
            target_limit
        )

        if reviews:

            logger.info(
                f"✅ SELENIUMBASE SUCCESS => {len(reviews)}"
            )

            return reviews

        logger.warning(
            "⚠️ SELENIUMBASE FAILED"
        )

        reviews = await asyncio.to_thread(
            scrape_with_requests,
            place_id
        )

        if reviews:

            logger.info(
                f"✅ REQUESTS SUCCESS => {len(reviews)}"
            )

            return reviews

        logger.warning(
            "⚠️ ALL ENGINES FAILED"
        )

        return []

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
```

# .env

```env
SERPAPI_API_KEY=YOUR_NEW_SERPAPI_KEY
PROXY_URL=http://username:password@host:port
```

# requirements.txt additions

```txt
requests
beautifulsoup4
lxml
fake-useragent
playwright
playwright-stealth
camoufox
seleniumbase
tenacity
```
