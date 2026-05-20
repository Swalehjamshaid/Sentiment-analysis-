# ==========================================================
# FILE: app/services/scraper.py
# CAMOUFOX + GOOGLE REVIEWS SCRAPER
# ADVANCED STEALTH VERSION — WORLD CLASS
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
from typing import Dict, Any, List
from fake_useragent import UserAgent
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential
)
from playwright.async_api import TimeoutError
from camoufox.async_api import AsyncCamoufox

# ==========================================================
logger = logging.getLogger("app.services.scraper")

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
MAX_SCROLLS = 220
MAX_IDLE_SCROLLS = 22
SCROLL_PAUSE_MIN = 2.8
SCROLL_PAUSE_MAX = 6.5

# Multi-language review keywords
REVIEW_WORDS = [
    "review", "reviews", "rating", "ratings", "avis", "bewertungen",
    "reseñas", "recensioni", "отзывы", "口コミ", "리뷰", "评论",
    "समीक्षा", "ביקורות", "รีวิว", "yorumlar"
]

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
    text = re.sub(r'\s+', ' ', text)
    return text[:5000]

def normalize_rating(value):
    try:
        match = re.search(r"([0-9.]+)", str(value))
        if match:
            return int(float(match.group(1)))
    except Exception:
        pass
    return 5

def generate_hash(author, text):
    raw = f"{author}_{text[:200]}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


# ==========================================================
# DETECT BLOCKING
# ==========================================================
async def detect_google_block(page):
    try:
        content = (await page.content()).lower()
        keywords = ["captcha", "unusual traffic", "not a robot", "/sorry/"]
        for keyword in keywords:
            if keyword in content:
                logger.warning(f"⚠️ GOOGLE BLOCK DETECTED: {keyword}")
                return True
        return False
    except Exception:
        return False


# ==========================================================
# HUMAN SCROLL
# ==========================================================
async def human_scroll(page):
    amount = random.randint(800, 1600)
    await page.mouse.wheel(0, amount)
    await asyncio.sleep(random.uniform(SCROLL_PAUSE_MIN, SCROLL_PAUSE_MAX))


# ==========================================================
# WARMUP SESSION
# ==========================================================
async def warmup_session(page):
    logger.info("🔥 WARMING SESSION")
    await page.goto("https://www.google.com", wait_until="domcontentloaded", timeout=120000)
    await asyncio.sleep(6)
    await human_scroll(page)


# ==========================================================
# SAVE DEBUG INFO
# ==========================================================
async def save_debug_info(page, prefix="debug"):
    try:
        await page.screenshot(path=f"/tmp/{prefix}.png", full_page=True)
        html = await page.content()
        with open(f"/tmp/{prefix}.html", "w", encoding="utf-8") as f:
            f.write(html)
        logger.info(f"📸📄 Debug saved: {prefix}")
    except Exception as e:
        logger.debug(f"Debug save failed: {e}")


# ==========================================================
# OPEN REVIEWS PANEL — ULTRA ROBUST
# ==========================================================
async def open_reviews_panel(page):
    logger.info("📦 OPENING REVIEWS PANEL — ADVANCED STRATEGY")
    await asyncio.sleep(12)

    strategies = [
        'button[aria-label*="Reviews" i]',
        'button[aria-label*="review" i]',
        'button[data-value="Reviews"]',
        '//button[contains(translate(text(),"ABCDEFGHIJKLMNOPQRSTUVWXYZ","abcdefghijklmnopqrstuvwxyz"), "review")]',
        'div[role="tab"]',
    ]

    for selector in strategies:
        try:
            if selector.startswith('//'):
                elements = await page.query_selector_all(f"xpath={selector}")
            else:
                elements = await page.query_selector_all(selector)

            for element in elements:
                try:
                    text = safe_string(await element.inner_text()).lower()
                    aria = safe_string(await element.get_attribute("aria-label")).lower()
                    combined = f"{text} {aria}"

                    if any(word in combined for word in REVIEW_WORDS):
                        await element.scroll_into_view_if_needed()
                        await asyncio.sleep(2)
                        await element.click(timeout=15000)
                        logger.info("✅ Reviews panel opened")
                        await asyncio.sleep(10)
                        return True
                except:
                    continue
        except Exception:
            continue

    # Aggressive Fallback
    logger.warning("⚠️ Standard strategies failed → AGGRESSIVE FALLBACK")
    try:
        all_buttons = await page.query_selector_all("button, div[role='tab'], span")
        for el in all_buttons[:180]:
            try:
                text = safe_string(await el.inner_text()).lower()
                aria = safe_string(await el.get_attribute("aria-label")).lower()
                if any(word in text or word in aria for word in REVIEW_WORDS):
                    await el.scroll_into_view_if_needed()
                    await asyncio.sleep(2)
                    await el.click(timeout=12000)
                    await asyncio.sleep(10)
                    logger.info("✅ Reviews opened via aggressive fallback")
                    return True
            except:
                continue
    except Exception as e:
        logger.exception(f"Aggressive fallback error: {e}")

    logger.error("❌ FAILED TO OPEN REVIEWS PANEL")
    await save_debug_info(page, "review_panel_failed")
    return False


# ==========================================================
# SORT BY NEWEST
# ==========================================================
async def sort_by_newest(page):
    try:
        logger.info("🔄 Sorting by Newest...")
        sort_btn = await page.wait_for_selector('//button[contains(@aria-label,"Sort") or contains(.,"Sort")]', timeout=8000)
        await sort_btn.click()
        await asyncio.sleep(2.5)

        newest_option = await page.wait_for_selector('//li[contains(.,"Newest") or contains(.,"Neueste")]', timeout=8000)
        await newest_option.click()
        logger.info("✅ Sorted by Newest")
        await asyncio.sleep(7)
        return True
    except Exception as e:
        logger.warning(f"Sort by Newest failed (continuing): {e}")
        return False


# ==========================================================
# EXPAND & EXTRACT
# ==========================================================
async def expand_reviews(page):
    for sel in ['button.w8nwRe', 'button[jsaction*="expandReview"]']:
        try:
            buttons = await page.query_selector_all(sel)
            for btn in buttons:
                await btn.click()
        except:
            pass


async def extract_reviews(page, target_limit=500):
    logger.info("📦 STARTING REVIEW EXTRACTION")
    reviews = []
    seen_ids = set()
    idle_scrolls = 0
    previous_count = 0

    for scroll in range(MAX_SCROLLS):
        try:
            await expand_reviews(page)

            cards = await page.query_selector_all('div[data-review-id], div.jftiEf, div[role="article"]')

            for card in cards:
                try:
                    author = ""
                    review_text = ""
                    rating = 5

                    # Author
                    for sel in ['.d4r55', '.TSUbDb']:
                        try:
                            el = await card.query_selector(sel)
                            if el:
                                author = clean_text(await el.inner_text())
                                break
                        except:
                            pass

                    # Text
                    for sel in ['.wiI7pd', '.MyEned']:
                        try:
                            el = await card.query_selector(sel)
                            if el:
                                review_text = clean_text(await el.inner_text())
                                break
                        except:
                            pass

                    if not review_text:
                        continue

                    # Rating
                    for sel in ['span[aria-label*="star"]', 'span.kvMYJc']:
                        try:
                            el = await card.query_selector(sel)
                            if el:
                                label = await el.get_attribute("aria-label")
                                rating = normalize_rating(label)
                                break
                        except:
                            pass

                    review_id = generate_hash(author, review_text)
                    if review_id in seen_ids:
                        continue
                    seen_ids.add(review_id)

                    reviews.append({
                        "review_id": review_id,
                        "author_name": author or "Anonymous",
                        "rating": rating,
                        "text": review_text
                    })
                except:
                    continue

            logger.info(f"✅ TOTAL REVIEWS: {len(reviews)} | Scroll {scroll}")

            if len(reviews) >= target_limit:
                break

            await human_scroll(page)

            current_count = len(reviews)
            if current_count == previous_count:
                idle_scrolls += 1
            else:
                idle_scrolls = 0
            previous_count = current_count

            if idle_scrolls >= MAX_IDLE_SCROLLS:
                logger.warning("⚠️ IDLE SCROLL LIMIT REACHED")
                break

        except Exception as e:
            logger.exception(f"❌ Extraction error: {e}")

    gc.collect()
    return reviews


# ==========================================================
# MAIN SCRAPER
# ==========================================================
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2.5, min=4, max=25))
async def scrape_google_reviews(business_name: str, target_limit: int = 500):
    browser = None
    try:
        proxy = {
            "server": PROXY_SERVER,
            "username": PROXY_USERNAME,
            "password": PROXY_PASSWORD
        }

        logger.info("🚀 STARTING CAMOUFOX ADVANCED STEALTH")
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
            timezone_id="Asia/Karachi",
            user_agent=UserAgent().random,
            viewport={"width": 1440, "height": 960}
        )

        page = await context.new_page()

        # Proxy Check
        await page.goto("https://ipinfo.io/json", wait_until="domcontentloaded", timeout=90000)
        logger.info(f"🌐 PROXY ACTIVE")

        await warmup_session(page)

        # Search
        maps_url = f"https://www.google.com/maps/search/{business_name.replace(' ', '+')}"
        await page.goto(maps_url, wait_until="domcontentloaded", timeout=120000)
        await asyncio.sleep(15)

        if await detect_google_block(page):
            return []

        # Click Business Result
        clicked = False
        business_selectors = ['a.hfpxzc', 'div.Nv2PK', 'div[role="article"]', 'a[href*="/maps/place/"]']
        for selector in business_selectors:
            try:
                results = await page.query_selector_all(selector)
                if results:
                    await results[0].scroll_into_view_if_needed()
                    await results[0].click(timeout=15000)
                    clicked = True
                    await asyncio.sleep(18)
                    break
            except:
                continue

        if not clicked:
            logger.warning("⚠️ BUSINESS CLICK FAILED")
            await save_debug_info(page, "business_click_failed")
            return []

        # Open Reviews + Sort
        opened = await open_reviews_panel(page)
        if not opened:
            return []

        await sort_by_newest(page)

        # Extract
        reviews = await extract_reviews(page, target_limit)
        logger.info(f"✅ SUCCESSFULLY SCRAPED {len(reviews)} REVIEWS")
        return reviews

    except Exception as e:
        logger.exception(f"❌ SCRAPER FAILED: {e}")
        return []
    finally:
        try:
            if browser:
                await browser.close()
        except:
            pass
