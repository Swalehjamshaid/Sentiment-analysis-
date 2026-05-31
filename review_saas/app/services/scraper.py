# =========================================================
# FILE: app/services/scraper.py
# QUANTUM ENTERPRISE GOOGLE REVIEW SCRAPER
# PATCHRIGHT + PLAYWRIGHT STEALTH + CRAWL4AI
# FULLY ALIGNED WITH review.py
# VERSION: 15.0 - ALL CRITICAL FIXES APPLIED
# =========================================================

from __future__ import annotations

# =========================================================
# STANDARD LIBRARIES
# =========================================================

import os
import re
import time
import random
import asyncio
import hashlib
import logging
import traceback
import secrets

from datetime import datetime

from typing import (
    Dict,
    List,
    Any,
    Tuple,
    Optional
)

# =========================================================
# LOGGER
# =========================================================

logger = logging.getLogger(__name__)

logger.setLevel(logging.INFO)

print("🚀 QUANTUM ENTERPRISE SCRAPER V15.0 BOOTING - CRITICAL FIXES APPLIED")

# =========================================================
# CACHE
# =========================================================

from cachetools import TTLCache

review_cache = TTLCache(
    maxsize=2000,
    ttl=3600
)

# =========================================================
# TENACITY
# =========================================================

from tenacity import (
    retry,
    stop_after_attempt,
    wait_random_exponential
)

# =========================================================
# BACKOFF
# =========================================================

import backoff

# =========================================================
# SELECTOLAX
# =========================================================

SELECTOLAX_AVAILABLE = False

try:

    from selectolax.parser import HTMLParser

    SELECTOLAX_AVAILABLE = True

    logger.info(
        "✅ SELECTOLAX READY"
    )

except Exception as e:

    logger.error(
        f"❌ SELECTOLAX ERROR => {e}"
    )

# =========================================================
# BEAUTIFULSOUP
# =========================================================

BS4_AVAILABLE = False

try:

    from bs4 import BeautifulSoup

    BS4_AVAILABLE = True

    logger.info(
        "✅ BS4 READY"
    )

except Exception as e:

    logger.error(
        f"❌ BS4 ERROR => {e}"
    )

# =========================================================
# CURL_CFFI
# =========================================================

CURL_CFFI_AVAILABLE = False

try:

    from curl_cffi import requests as curl_requests

    CURL_CFFI_AVAILABLE = True

    logger.info(
        "✅ CURL_CFFI READY"
    )

except Exception as e:

    logger.error(
        f"❌ CURL_CFFI ERROR => {e}"
    )

# =========================================================
# PATCHRIGHT
# =========================================================

PATCHRIGHT_AVAILABLE = False

try:

    from patchright.async_api import (
        async_playwright,
        TimeoutError as PlaywrightTimeoutError
    )

    PATCHRIGHT_AVAILABLE = True

    logger.info(
        "✅ PATCHRIGHT READY"
    )

except Exception as e:

    logger.error(
        f"❌ PATCHRIGHT ERROR => {e}"
    )

# =========================================================
# PLAYWRIGHT STEALTH
# =========================================================

STEALTH_AVAILABLE = False

try:

    from playwright_stealth import stealth_async

    STEALTH_AVAILABLE = True

    logger.info(
        "✅ STEALTH READY"
    )

except Exception as e:

    logger.error(
        f"❌ STEALTH ERROR => {e}"
    )

# =========================================================
# CRAWL4AI
# =========================================================

CRAWL4AI_AVAILABLE = False

try:

    from crawl4ai import AsyncWebCrawler

    CRAWL4AI_AVAILABLE = True

    logger.info(
        "✅ CRAWL4AI READY"
    )

except Exception as e:

    logger.error(
        f"❌ CRAWL4AI ERROR => {e}"
    )

# =========================================================
# FAKE USER AGENT
# =========================================================

FAKE_UA_AVAILABLE = False

try:

    from fake_useragent import UserAgent

    fake_ua = UserAgent()

    FAKE_UA_AVAILABLE = True

except Exception:

    fake_ua = None

# =========================================================
# ENVIRONMENT VARIABLES
# =========================================================

SCRAPER_TIMEOUT = int(
    os.getenv(
        "SCRAPER_TIMEOUT",
        "180"
    )
)

MAX_REVIEWS = int(
    os.getenv(
        "SCRAPER_MAX_REVIEWS",
        "100"
    )
)

HEADLESS_MODE = os.getenv(
    "SCRAPER_HEADLESS",
    "true"
).lower() == "true"

# CRITICAL FIX #7: Persistent browser profile directory
USER_DATA_DIR = os.getenv(
    "USER_DATA_DIR",
    "/tmp/chrome_profile"
)

try:
    os.makedirs(USER_DATA_DIR, exist_ok=True)
    logger.info(f"✅ Persistent profile directory: {USER_DATA_DIR}")
except Exception as e:
    logger.warning(f"⚠️ Could not create profile directory: {e}")

# =========================================================
# PROXY CONFIGURATION
# =========================================================

PROXY_SERVER = os.getenv(
    "PROXY_SERVER",
    ""
).strip()

PROXY_USERNAME = os.getenv(
    "PROXY_USERNAME",
    ""
).strip()

PROXY_PASSWORD = os.getenv(
    "PROXY_PASSWORD",
    ""
).strip()

PROXY_POOL = []

FAILED_PROXIES = set()

PROXY_HEALTH = {}

# Support for multiple proxies (comma-separated)
if "," in PROXY_SERVER:
    for proxy in PROXY_SERVER.split(","):
        proxy = proxy.strip()
        if proxy:
            PROXY_POOL.append({
                "server": f"http://{proxy}",
                "username": PROXY_USERNAME,
                "password": PROXY_PASSWORD
            })
elif PROXY_SERVER:
    PROXY_POOL.append({
        "server": f"http://{PROXY_SERVER}",
        "username": PROXY_USERNAME,
        "password": PROXY_PASSWORD
    })

logger.info(
    f"✅ PROXY COUNT => {len(PROXY_POOL)}"
)

# =========================================================
# CONCURRENCY
# =========================================================

SCRAPER_SEMAPHORE = asyncio.Semaphore(2)

# =========================================================
# HELPERS
# =========================================================

def utc_now():

    return datetime.utcnow()


def quantum_entropy():

    return secrets.randbelow(
        1000000
    )


async def quantum_delay():

    entropy = quantum_entropy()

    delay = (
        (entropy % 3000) / 1000
    )

    await asyncio.sleep(
        max(0.5, delay)
    )


def maps_url(
    place_id: str
):

    return (
        "https://www.google.com/maps/place/"
        f"?q=place_id:{place_id}"
    )


def get_user_agent():

    static_agents = [

        (
            "Mozilla/5.0 "
            "(Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/125.0 Safari/537.36"
        ),

        (
            "Mozilla/5.0 "
            "(Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/124.0 Safari/537.36"
        )
    ]

    if FAKE_UA_AVAILABLE and fake_ua:

        try:

            return fake_ua.random

        except Exception:
            pass

    return random.choice(
        static_agents
    )

# =========================================================
# ENHANCED CAPTCHA DETECTION (CRITICAL FIX #9)
# =========================================================

def detect_captcha(
    html: str
):

    html_lower = html.lower()

    patterns = [

        "captcha",
        "unusual traffic",
        "not a robot",
        "sorry",
        "verify you are human",
        "security check",
        "access denied",
        "automated queries",
        "rate limit"
    ]

    return any(
        p in html_lower
        for p in patterns
    )

# =========================================================
# PROXY INTELLIGENCE (IMPROVED SCORING)
# =========================================================

def score_proxy(
    proxy_server: str
):

    stats = PROXY_HEALTH.get(
        proxy_server,
        {
            "success": 1,
            "fail": 1,
            "captcha": 0
        }
    )

    success_rate = stats["success"] / (stats["success"] + stats["fail"])
    captcha_rate = stats["captcha"] / (stats["success"] + stats["fail"] + stats["captcha"] + 1)
    
    # Advanced scoring: 60% success, 30% captcha penalty
    return (success_rate * 0.6) - (captcha_rate * 0.3)


def update_proxy_score(
    proxy_server: str,
    success: bool,
    captcha: bool = False
):

    if proxy_server not in PROXY_HEALTH:

        PROXY_HEALTH[proxy_server] = {

            "success": 1,
            "fail": 1,
            "captcha": 0
        }

    if success:

        PROXY_HEALTH[
            proxy_server
        ]["success"] += 1

    else:

        PROXY_HEALTH[
            proxy_server
        ]["fail"] += 1
        
    if captcha:
        PROXY_HEALTH[
            proxy_server
        ]["captcha"] += 1


def get_best_proxy():

    try:

        available = [

            p for p in PROXY_POOL
            if p["server"] not in FAILED_PROXIES
        ]

        if not available:

            return None

        scored = sorted(

            available,

            key=lambda p: score_proxy(
                p["server"]
            ),

            reverse=True
        )

        return scored[0]

    except Exception:

        return None

# =========================================================
# REVIEW NORMALIZATION
# =========================================================

def generate_review_id(
    place_id: str,
    author: str,
    text: str
):

    raw = f"{place_id}:{author}:{text}"

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()


def normalize_review(
    review: Dict[str, Any],
    place_id: str
):

    try:

        review_text = str(

            review.get(
                "review_text",

                review.get(
                    "text",

                    review.get(
                        "content",
                        ""
                    )
                )
            )

        ).strip()

        if not review_text:

            return None

        author = str(

            review.get(
                "author",

                review.get(
                    "author_name",
                    "Anonymous"
                )
            )

        ).strip()

        if not author:

            author = "Anonymous"

        rating = review.get(
            "rating",
            5
        )

        try:

            rating = int(float(rating))

        except Exception:

            rating = 5

        rating = max(
            1,
            min(rating, 5)
        )

        return {

            "google_review_id":
                generate_review_id(
                    place_id,
                    author,
                    review_text
                ),

            "author":
                author,

            "author_name":
                author,

            "rating":
                rating,

            "review_text":
                review_text,

            "content":
                review_text,

            "text":
                review_text,

            "sentiment_score":
                0.5,

            "google_review_time":
                utc_now(),

            "scraped_at":
                utc_now()
        }

    except Exception as e:

        logger.error(
            f"❌ NORMALIZE ERROR => {e}"
        )

        return None

# =========================================================
# DEDUPLICATION
# =========================================================

def deduplicate_reviews(
    reviews: List[Dict]
):

    seen = set()

    unique = []

    for review in reviews:

        review_id = review.get(
            "google_review_id",
            ""
        )

        if not review_id:
            continue

        if review_id in seen:
            continue

        seen.add(review_id)

        unique.append(review)

    return unique

# =========================================================
# DEBUG HELPERS
# =========================================================

async def debug_page(
    page,
    stage: str,
    place_id: str = None
):

    try:

        logger.info(
            f"🔥 PAGE URL [{stage}] => {page.url}"
        )

        logger.info(
            f"🔥 PAGE TITLE [{stage}] => {await page.title()}"
        )
        
        # Get HTML length for debugging
        html = await page.content()
        logger.info(
            f"🔥 HTML LENGTH [{stage}] => {len(html)} bytes"
        )

        # Save debug files when no reviews found
        if stage == "after_extraction" and place_id:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            html_path = f"debug_{place_id}_{timestamp}.html"
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html)
            logger.info(f"📄 HTML saved: {html_path}")

        await page.screenshot(

            path=f"debug_{stage}.png",

            full_page=True
        )

    except Exception as e:

        logger.error(
            f"❌ DEBUG ERROR => {e}"
        )

# =========================================================
# CRITICAL FIX #4: REVIEW PANEL VALIDATION
# =========================================================

async def verify_review_panel(page) -> Tuple[bool, str]:
    """Verify review panel exists with multiple selectors"""
    
    panel_selectors = [
        (".m6QErb", "m6QErb"),
        ("[role='dialog'] .m6QErb", "dialog_panel"),
        ("[role='main']", "main_panel"),
        (".section-scrollbox", "scrollbox"),
        ("div[aria-label*='Reviews']", "aria_reviews")
    ]
    
    for selector, name in panel_selectors:
        try:
            exists = await page.evaluate(f"""
                () => {{
                    const panel = document.querySelector('{selector}');
                    return !!panel;
                }}
            """)
            
            if exists:
                logger.info(f"✅ REVIEW PANEL FOUND: {name} ({selector})")
                return True, name
        except:
            continue
    
    logger.warning("⚠️ NO REVIEW PANEL FOUND with any selector")
    return False, "none"

# =========================================================
# CRITICAL FIX #6: ENHANCED REVIEW PANEL SCROLLING
# =========================================================

async def scroll_review_panel_enhanced(page, max_scrolls: int = 30) -> int:
    """Enhanced scrolling with proper panel detection"""
    
    scroll_count = 0
    last_height = 0
    no_change_count = 0
    
    for i in range(max_scrolls):
        try:
            result = await page.evaluate("""
                () => {
                    // Try multiple panel selectors
                    const selectors = ['.m6QErb', '[role="main"]', '.section-scrollbox'];
                    let panel = null;
                    
                    for (const sel of selectors) {
                        panel = document.querySelector(sel);
                        if (panel) break;
                    }
                    
                    if (panel) {
                        const currentHeight = panel.scrollHeight;
                        panel.scrollTop = panel.scrollHeight;
                        return { success: true, height: currentHeight };
                    }
                    return { success: false, height: 0 };
                }
            """)
            
            if result and result.get('success'):
                current_height = result.get('height', 0)
                
                if current_height == last_height:
                    no_change_count += 1
                    if no_change_count >= 3:
                        logger.info(f"📊 Scroll complete after {scroll_count} scrolls")
                        break
                else:
                    no_change_count = 0
                    last_height = current_height
                
                scroll_count += 1
                await asyncio.sleep(random.uniform(1.0, 1.5))
            else:
                break
                
        except Exception as e:
            logger.debug(f"Scroll error: {e}")
            break
    
    logger.info(f"📊 TOTAL SCROLLS: {scroll_count}")
    return scroll_count

# =========================================================
# CRITICAL FIX #8: EXPAND TRUNCATED REVIEWS
# =========================================================

async def expand_truncated_reviews(page) -> int:
    """Click all 'More' and 'Read more' buttons"""
    
    expanded_count = 0
    
    expand_selectors = [
        'button:has-text("More")',
        'button:has-text("more")',
        'span:has-text("More")',
        'button:has-text("Read more")',
        'span:has-text("Read more")',
        'span.w8nwRe',
        'button[jsaction*="expand"]'
    ]
    
    for selector in expand_selectors:
        try:
            buttons = await page.locator(selector).all()
            for button in buttons:
                try:
                    await button.click()
                    expanded_count += 1
                    await asyncio.sleep(0.3)
                except:
                    pass
        except:
            pass
    
    if expanded_count > 0:
        logger.info(f"✅ Expanded {expanded_count} truncated reviews")
    
    return expanded_count

# =========================================================
# CRITICAL FIX #2 & #5: MULTI-SELECTOR REVIEW BUTTON CLICKING
# =========================================================

async def click_reviews_button_with_fallback(page, place_id: str) -> Tuple[bool, str]:
    """Multiple strategies to click reviews button"""
    
    # Strategy 1: Direct selector clicking
    review_button_selectors = [
        'button[jsaction*="pane.reviewChart.moreReviews"]',
        'button[aria-label*="reviews"]',
        'button[aria-label*="Reviews"]',
        'button[aria-label*="Review"]',
        'button[jsaction*="reviews"]',
        'button[data-tab-index="1"]',
        '[role="tab"][aria-label*="Reviews"]',
        '[data-value="Reviews"]',
        'button[jsaction*="pane.rating.moreReviews"]',
        'button[aria-label*="Google reviews"]',
        'button[role="tab"]'
    ]
    
    # Try each selector
    for selector in review_button_selectors:
        try:
            locator = page.locator(selector).first
            count = await locator.count()
            
            if count > 0:
                await locator.click()
                logger.info(f"✅ CLICKED REVIEW BUTTON: {selector}")
                await asyncio.sleep(3)
                logger.info(f"📊 URL AFTER CLICK: {page.url}")
                return True, selector
        except Exception as e:
            logger.debug(f"Selector failed: {selector} - {e}")
    
    # Strategy 2: Try alternate URL
    logger.info("🔄 Trying alternate reviews URL...")
    alt_url = f"https://search.google.com/local/reviews?placeid={place_id}"
    
    try:
        await page.goto(alt_url, wait_until="networkidle", timeout=30000)
        await asyncio.sleep(3)
        logger.info(f"📊 ALTERNATE URL LOADED: {page.url}")
        return True, "alternate_url"
    except Exception as e:
        logger.error(f"Alternate URL failed: {e}")
    
    logger.error("❌ ALL REVIEW BUTTON STRATEGIES FAILED")
    return False, "none"

# =========================================================
# PATCHRIGHT PROVIDER - UPDATED WITH CRITICAL FIXES
# =========================================================

@backoff.on_exception(
    backoff.expo,
    Exception,
    max_time=300
)
async def patchright_reviews(
    place_id: str
):

    reviews = []

    if not PATCHRIGHT_AVAILABLE:

        logger.error(
            "❌ PATCHRIGHT NOT AVAILABLE"
        )

        return reviews

    async with SCRAPER_SEMAPHORE:

        context = None

        for attempt in range(3):

            proxy = get_best_proxy()
            start_time = time.time()

            try:

                logger.info(
                    f"🔥 PATCHRIGHT ATTEMPT => {attempt+1}"
                )

                logger.info(
                    f"🔥 ACTIVE PROXY => {proxy}"
                )

                async with async_playwright() as p:

                    # CRITICAL FIX #1 & #7: Use chromium channel with persistent context
                    logger.info("🚀 LAUNCHING PATCHRIGHT BROWSER (chromium channel)")
                    
                    context = await p.chromium.launch_persistent_context(
                        user_data_dir=USER_DATA_DIR,
                        headless=HEADLESS_MODE,
                        proxy=proxy,
                        channel="chromium",  # CRITICAL FIX #1: chromium, not chrome
                        args=[
                            "--disable-blink-features=AutomationControlled",
                            "--disable-dev-shm-usage",
                            "--disable-gpu",
                            "--window-size=1920,1080",
                            "--no-sandbox",
                            "--disable-web-security",
                            "--disable-features=IsolateOrigins,site-per-process",
                            "--disable-site-isolation-trials",
                            "--disable-infobars",
                            "--start-maximized",
                            "--disable-extensions",
                            "--disable-popup-blocking"
                        ]
                    )
                    
                    logger.info("✅ PATCHRIGHT BROWSER LAUNCHED SUCCESSFULLY")
                    
                    # Get or create page
                    page = context.pages[0] if context.pages else await context.new_page()

                    await page.add_init_script(
                        """
                        Object.defineProperty(
                            navigator,
                            'webdriver',
                            {
                                get: () => undefined
                            }
                        );
                        """
                    )

                    if STEALTH_AVAILABLE:

                        try:

                            await stealth_async(page)

                        except Exception:
                            pass

                    target_url = maps_url(
                        place_id
                    )

                    logger.info(
                        f"🔥 TARGET URL => {target_url}"
                    )

                    await page.goto(

                        target_url,

                        wait_until="networkidle",

                        timeout=180000
                    )
                    
                    # CRITICAL FIX #3: Validate page loaded
                    page_title = await page.title()
                    logger.info(f"📊 PAGE TITLE: {page_title}")
                    
                    if "Google Maps" == page_title:
                        logger.error(f"❌ INVALID PLACE ID: {place_id}")
                        await page.screenshot(path=f"invalid_place_{place_id}.png", full_page=True)
                        return []

                    await page.wait_for_timeout(
                        random.randint(
                            4000,
                            9000
                        )
                    )

                    await debug_page(
                        page,
                        "before_reviews",
                        place_id
                    )

                    # CRITICAL FIX #2 & #5: Enhanced button clicking
                    clicked, method = await click_reviews_button_with_fallback(page, place_id)

                    if not clicked:
                        logger.error("❌ REVIEW BUTTON NOT FOUND")
                        await page.screenshot(path=f"no_button_{place_id}.png", full_page=True)
                        return reviews

                    await page.wait_for_timeout(
                        8000
                    )

                    await debug_page(
                        page,
                        "after_review_click",
                        place_id
                    )

                    html = await page.content()

                    if detect_captcha(html):

                        logger.error(
                            "❌ CAPTCHA DETECTED"
                        )
                        
                        if proxy:
                            update_proxy_score(
                                proxy["server"],
                                False,
                                captcha=True
                            )

                        return reviews

                    # CRITICAL FIX #4: Verify review panel
                    panel_found, panel_name = await verify_review_panel(page)
                    if not panel_found:
                        logger.error("❌ REVIEW PANEL NOT FOUND")
                        await page.screenshot(path=f"no_panel_{place_id}.png", full_page=True)
                        return reviews

                    # CRITICAL FIX #6: Enhanced scrolling
                    scrolls = await scroll_review_panel_enhanced(page, max_scrolls=25)
                    logger.info(f"📊 SCROLLED {scrolls} times")
                    
                    # CRITICAL FIX #8: Expand truncated reviews
                    expanded = await expand_truncated_reviews(page)
                    logger.info(f"📊 EXPANDED {expanded} truncated reviews")
                    
                    await page.wait_for_timeout(2000)

                    # CRITICAL FIX #5 & #6: Enhanced review card selectors
                    review_selectors = [

                        "div[data-review-id]",  # Most reliable
                        "div[role='article']",   # Semantic
                        "div.jftiEf",
                        "div.MyEned",
                        "div[class*=review]",
                        "div[class*=fontBodyMedium]"
                    ]

                    cards = None

                    for selector in review_selectors:

                        try:

                            locator = page.locator(
                                selector
                            )

                            count = await locator.count()

                            logger.info(
                                f"🔥 REVIEW SELECTOR {selector} => {count}"
                            )

                            if count > 0:

                                cards = locator

                                break

                        except Exception:
                            continue

                    if cards is None:

                        logger.error(
                            "❌ NO REVIEW CARDS FOUND"
                        )
                        
                        await debug_page(page, "no_cards", place_id)

                        return reviews

                    # Count cards before extraction
                    total_cards = await cards.count()
                    logger.info(f"🔥 TOTAL CARDS FOUND: {total_cards}")

                    previous_count = 0

                    no_growth = 0

                    while no_growth < 8 and previous_count < MAX_REVIEWS:

                        try:

                            # Use proper panel scrolling
                            await scroll_review_panel_enhanced(page, max_scrolls=3)

                            await quantum_delay()

                            current_count = await cards.count()

                            logger.info(
                                f"🔥 REVIEW COUNT => {current_count}"
                            )

                            if current_count == previous_count:

                                no_growth += 1

                            else:

                                no_growth = 0

                            previous_count = current_count

                            if current_count >= MAX_REVIEWS:

                                break

                        except Exception as e:

                            logger.error(
                                f"❌ SCROLL ERROR => {e}"
                            )

                            break

                    total_cards = await cards.count()

                    logger.info(
                        f"🔥 FINAL CARD COUNT => {total_cards}"
                    )

                    total_cards = min(
                        total_cards,
                        MAX_REVIEWS
                    )

                    for index in range(total_cards):

                        try:

                            card = cards.nth(index)

                            author = "Anonymous"

                            text = ""

                            rating = 5

                            try:

                                # Enhanced author selectors
                                author_selectors = [

                                    ".d4r55",
                                    ".TSUbDb",
                                    "span[class*=author]",
                                    "[data-author-name]"
                                ]

                                for selector in author_selectors:

                                    locator = card.locator(
                                        selector
                                    )

                                    if await locator.count() > 0:

                                        author = (
                                            await locator
                                            .first
                                            .inner_text()
                                        ).strip()

                                        break

                            except Exception:
                                pass

                            try:

                                # Enhanced text selectors
                                text_selectors = [

                                    ".wiI7pd",
                                    ".MyEned",
                                    "span[jsname]",
                                    "[data-review-text]"
                                ]

                                for selector in text_selectors:

                                    locator = card.locator(
                                        selector
                                    )

                                    if await locator.count() > 0:

                                        text = (
                                            await locator
                                            .first
                                            .inner_text()
                                        ).strip()

                                        break

                            except Exception:
                                pass

                            try:

                                rating_locator = card.locator(
                                    "span.kvMYJc"
                                )

                                if await rating_locator.count() > 0:

                                    aria = await rating_locator.get_attribute(
                                        "aria-label"
                                    )

                                    if aria:

                                        match = re.search(
                                            r"(\d)",
                                            aria
                                        )

                                        if match:

                                            rating = int(
                                                match.group(1)
                                            )

                            except Exception:
                                pass

                            normalized = normalize_review({

                                "author":
                                    author,

                                "rating":
                                    rating,

                                "review_text":
                                    text

                            }, place_id)

                            if normalized:

                                reviews.append(
                                    normalized
                                )

                        except Exception as e:

                            logger.error(
                                f"❌ REVIEW PARSE ERROR => {e}"
                            )

                    logger.info(
                        f"✅ PATCHRIGHT REVIEWS => {len(reviews)}"
                    )

                    if proxy:

                        update_proxy_score(
                            proxy["server"],
                            True
                        )

                    if reviews:

                        break

            except Exception as e:

                logger.error(
                    f"❌ PATCHRIGHT ERROR => {e}"
                )

                logger.error(
                    traceback.format_exc()
                )

                if proxy:

                    update_proxy_score(
                        proxy["server"],
                        False
                    )

                await asyncio.sleep(
                    random.uniform(3, 8)
                )

            finally:

                try:

                    if context:

                        await context.close()

                except Exception:
                    pass

    return reviews

# =========================================================
# MASTER SCRAPER - WITH SAFE CACHE (CRITICAL FIX #8)
# =========================================================

async def scrape_google_reviews(
    place_id: str
):

    logger.info(
        f"🚀 MASTER SCRAPER => {place_id}"
    )

    if not place_id:

        return []

    cache_key = f"reviews:{place_id}"

    try:

        cached = review_cache.get(
            cache_key
        )

        # CRITICAL FIX #8: Only return cache if it has reviews
        if cached and len(cached) > 0:

            logger.info(
                f"⚡ CACHE HIT ({len(cached)} reviews)"
            )

            return cached
        elif cached:
            logger.warning(f"⚠️ CACHE HAD EMPTY RESULT, ignoring")
            # Remove empty cache entry
            try:
                del review_cache[cache_key]
            except:
                pass

    except Exception:
        pass

    all_reviews = []

    try:

        result = await asyncio.wait_for(

            patchright_reviews(
                place_id
            ),

            timeout=300
        )

        if isinstance(
            result,
            list
        ):

            all_reviews.extend(
                result
            )

    except Exception as e:

        logger.error(
            f"❌ SCRAPER ERROR => {e}"
        )

    all_reviews = deduplicate_reviews(
        all_reviews
    )

    all_reviews = all_reviews[:MAX_REVIEWS]

    # CRITICAL FIX #8: Only cache non-empty results
    if all_reviews and len(all_reviews) > 0:
        try:

            review_cache[
                cache_key
            ] = all_reviews
            
            logger.info(f"💾 CACHED {len(all_reviews)} reviews")

        except Exception:
            pass
    else:
        logger.warning(f"⚠️ NOT CACHING empty result for {place_id}")

    logger.info(
        f"✅ FINAL REVIEWS => {len(all_reviews)}"
    )

    return all_reviews

# =========================================================
# ALIAS
# =========================================================

async def run_scraper(
    place_id: str
):

    return await scrape_google_reviews(
        place_id
    )

# =========================================================
# READY
# =========================================================

logger.info(
    "✅ QUANTUM PATCHRIGHT SCRAPER V15.0 READY"
)
logger.info(f"📊 Persistent profile: {USER_DATA_DIR}")
logger.info(f"📊 Max reviews: {MAX_REVIEWS}")
logger.info(f"📊 Headless mode: {HEADLESS_MODE}")
