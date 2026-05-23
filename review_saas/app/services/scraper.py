# ==========================================================
# FILE: app/services/scraper.py
# TRUSTLYTICS AI — FINAL HYBRID SCRAPER (Updated)
# 100% COMPATIBLE WITH reviews.py & main.py
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
from datetime import datetime, timedelta

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
    from playwright.async_api import async_playwright
except Exception:
    async_playwright = None

try:
    from playwright_stealth import stealth_async
except Exception:
    stealth_async = None

# ==========================================================
# LOGGER
# ==========================================================
logger = logging.getLogger("app.services.scraper")

# ==========================================================
# ENV VARIABLES
# ==========================================================
SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY")
PROXY_SERVER = os.getenv("PROXY_SERVER")
PROXY_USERNAME = os.getenv("PROXY_USERNAME")
PROXY_PASSWORD = os.getenv("PROXY_PASSWORD")

# ==========================================================
# CONFIG
# ==========================================================
REQUEST_TIMEOUT = 120
PLAYWRIGHT_TIMEOUT = 70000
HEADLESS = True
MAX_SCROLLS = 10
PLAYWRIGHT_TARGET = 50

# ==========================================================
# HELPERS
# ==========================================================
def engine_available(engine):
    return engine is not None


def get_user_agent():
    try:
        if UserAgent:
            return UserAgent().random
    except:
        pass
    return ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/126.0 Safari/537.36")


def clean_text(text):
    if not text:
        return ""
    text = str(text)
    text = text.replace("\n", " ").replace("\r", " ").replace("\t", " ")
    return " ".join(text.split())[:5000]


def generate_hash(author, text):
    raw = f"{author}_{text}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def passes_date_filter(review_date, start_date=None):
    try:
        if not start_date:
            return True
        lower = review_date.lower()
        now = datetime.utcnow()
        if "day" in lower:
            num = int(re.search(r"\d+", lower).group())
            actual = now - timedelta(days=num)
        elif "week" in lower:
            num = int(re.search(r"\d+", lower).group())
            actual = now - timedelta(days=num * 7)
        elif "month" in lower:
            num = int(re.search(r"\d+", lower).group())
            actual = now - timedelta(days=num * 30)
        elif "year" in lower:
            num = int(re.search(r"\d+", lower).group())
            actual = now - timedelta(days=num * 365)
        else:
            actual = now
        return actual >= start_date
    except:
        return True


def get_proxy():
    try:
        session_id = random.randint(100000, 999999)
        username = f"{PROXY_USERNAME}-session-{session_id}"
        return {
            "server": f"http://{PROXY_SERVER}",
            "username": username,
            "password": PROXY_PASSWORD
        }
    except:
        return None


def get_requests_proxy():
    try:
        session_id = random.randint(100000, 999999)
        username = f"{PROXY_USERNAME}-session-{session_id}"
        proxy_url = f"http://{username}:{PROXY_PASSWORD}@{PROXY_SERVER}"
        return {"http": proxy_url, "https": proxy_url}
    except:
        return None


async def human_behavior(page):
    try:
        for _ in range(random.randint(2, 5)):
            await page.mouse.move(random.randint(100, 1400), random.randint(100, 900))
            await asyncio.sleep(random.uniform(0.4, 1.2))
    except:
        pass


async def detect_google_block(page):
    try:
        content = (await page.content()).lower()
        block_keywords = ["captcha", "unusual traffic", "automated queries", "/sorry/", "not a robot"]
        for keyword in block_keywords:
            if keyword in content:
                logger.warning(f"⚠️ GOOGLE BLOCK DETECTED => {keyword}")
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
    target_limit=50,
    start_date=None
):
    reviews = []
    existing_ids = existing_ids or set()

    if not engine_available(async_playwright):
        logger.warning("⚠️ Playwright not available")
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
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-gpu"
                ]
            )

            context = await browser.new_context(
                user_agent=get_user_agent(),
                locale="en-US",
                viewport={"width": random.randint(1280, 1920), "height": random.randint(800, 1080)}
            )

            page = await context.new_page()
            if engine_available(stealth_async):
                await stealth_async(page)

            url = f"https://www.google.com/maps/place/?q=place_id:{place_id}"
            logger.info(f"🚀 Playwright started for place_id: {place_id}")

            await page.goto(url, wait_until="domcontentloaded", timeout=PLAYWRIGHT_TIMEOUT)

            if await detect_google_block(page):
                return []

            await human_behavior(page)
            await asyncio.sleep(3)

            # Open reviews tab
            try:
                button = page.locator('button[jsaction*="pane.reviewChart.moreReviews"]')
                if await button.count() > 0:
                    await button.first.click()
                    await asyncio.sleep(3)
            except:
                pass

            # Scroll reviews
            review_feed = page.locator('div[role="feed"]')
            for _ in range(MAX_SCROLLS):
                try:
                    await review_feed.evaluate("(el) => el.scrollTop = el.scrollHeight")
                    await asyncio.sleep(random.uniform(1.2, 2.5))
                except:
                    pass

            # Extract reviews
            cards = page.locator("div.jftiEf")
            count = await cards.count()
            logger.info(f"📦 Playwright found {count} review cards")

            seen = set()
            for i in range(count):
                try:
                    card = cards.nth(i)

                    author = clean_text(await card.locator(".d4r55").inner_text())
                    text = clean_text(await card.locator(".wiI7pd").inner_text())
                    if not text:
                        continue

                    review_date = clean_text(await card.locator(".rsqaWe").inner_text())
                    if not passes_date_filter(review_date, start_date):
                        continue

                    rating = 5
                    try:
                        rating_text = await card.locator(".kvMYJc").get_attribute("aria-label")
                        match = re.search(r"(\d)", str(rating_text))
                        if match:
                            rating = int(match.group(1))
                    except:
                        pass

                    review_id = generate_hash(author, text)

                    if review_id in seen or review_id in existing_ids:
                        continue

                    seen.add(review_id)
                    existing_ids.add(review_id)

                    reviews.append({
                        "review_id": review_id,
                        "author_name": author,
                        "rating": rating,
                        "review_date": review_date,
                        "text": text,
                        "likes": 0
                    })

                    if len(reviews) >= target_limit:
                        break
                except:
                    continue

            logger.info(f"✅ Playwright extracted {len(reviews)} reviews")
            return reviews

    except Exception as e:
        logger.warning(f"⚠️ Playwright failed: {e}")
        return []
    finally:
        if browser:
            try:
                await browser.close()
            except:
                pass


# ==========================================================
# SERPAPI ENGINE
# ==========================================================
def serpapi_true_next_reviews(
    place_id,
    existing_ids=None,
    target_limit=100,
    start_date=None
):
    reviews = []
    existing_ids = existing_ids or set()
    seen = set()

    if not engine_available(requests) or not SERPAPI_API_KEY:
        logger.warning("⚠️ SERPAPI not configured")
        return reviews

    try:
        next_page_token = None
        total_new = 0

        while total_new < target_limit:
            params = {
                "engine": "google_maps_reviews",
                "place_id": place_id,
                "api_key": SERPAPI_API_KEY,
                "sort_by": "newestFirst",
                "hl": "en"
            }
            if next_page_token:
                params["next_page_token"] = next_page_token

            response = requests.get(
                "https://serpapi.com/search.json",
                params=params,
                timeout=REQUEST_TIMEOUT
            )
            response.raise_for_status()
            data = response.json()

            for review in data.get("reviews", []):
                try:
                    author = clean_text(review.get("user", {}).get("name", ""))
                    text = clean_text(review.get("snippet", ""))
                    if not text:
                        continue

                    review_date = clean_text(review.get("date", ""))
                    if not passes_date_filter(review_date, start_date):
                        continue

                    review_id = generate_hash(author, text)
                    if review_id in seen or review_id in existing_ids:
                        continue

                    seen.add(review_id)
                    existing_ids.add(review_id)

                    reviews.append({
                        "review_id": review_id,
                        "author_name": author,
                        "rating": review.get("rating", 5),
                        "review_date": review_date,
                        "text": text,
                        "likes": review.get("likes", 0)
                    })
                    total_new += 1
                    if total_new >= target_limit:
                        break
                except:
                    continue

            next_page_token = data.get("serpapi_pagination", {}).get("next_page_token")
            if not next_page_token:
                break
            time.sleep(random.uniform(1, 2.5))

        logger.info(f"✅ SERPAPI returned {len(reviews)} reviews")
        return reviews

    except Exception as e:
        logger.warning(f"⚠️ SERPAPI failed: {e}")
        return reviews


# ==========================================================
# MAIN SCRAPER
# ==========================================================
async def scrape_google_reviews(
    place_id: str,
    target_limit: int = 100,
    start_date=None,
    end_date=None
):
    logger.info(f"🚀 Starting hybrid scrape for place_id: {place_id} | Target: {target_limit}")

    try:
        existing_review_ids = set()

        # Layer 1: Playwright (Primary)
        playwright_reviews = await scrape_with_playwright(
            place_id=place_id,
            existing_ids=existing_review_ids,
            target_limit=min(PLAYWRIGHT_TARGET, target_limit),
            start_date=start_date
        )

        # Layer 2: SERPAPI Fallback
        remaining = target_limit - len(playwright_reviews)
        serp_reviews = []
        if remaining > 0:
            logger.info(f"🚀 Using SERPAPI fallback for {remaining} more reviews")
            serp_reviews = await asyncio.to_thread(
                serpapi_true_next_reviews,
                place_id,
                existing_review_ids,
                remaining,
                start_date
            )

        # Final deduplicated merge
        final_reviews = []
        seen = set()
        for review in playwright_reviews + serp_reviews:
            rid = review.get("review_id")
            if rid and rid not in seen:
                seen.add(rid)
                final_reviews.append(review)

        logger.info(f"✅ FINAL REVIEW COUNT => {len(final_reviews)}")
        return final_reviews

    except Exception as e:
        logger.exception(f"❌ SCRAPER FAILED => {e}")
        return []
    finally:
        gc.collect()
