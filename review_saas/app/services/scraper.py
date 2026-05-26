# =========================================================
# FILE: app/scraper.py
# TRUSTLYTICS AI - ULTRA ENTERPRISE REVIEW SCRAPER
# =========================================================
from __future__ import annotations
import os
import re
import json
import time
import asyncio
import logging
import traceback
import random
import hashlib
from datetime import datetime
from typing import List, Dict, Any

# =========================================================
# RETRY LIBRARIES
# =========================================================
from tenacity import retry, stop_after_attempt, wait_random_exponential
import backoff

# =========================================================
# LOGGER
# =========================================================
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# =========================================================
# ENVIRONMENT VARIABLES
# =========================================================
SERPAPI_KEY = os.getenv("SERPAPI_KEY", "").strip()
PROXY_USERNAME = os.getenv("PROXY_USERNAME", "").strip()
PROXY_PASSWORD = os.getenv("PROXY_PASSWORD", "").strip()
PROXY_SERVER = os.getenv("PROXY_SERVER", "").strip()

SCRAPER_TIMEOUT = int(os.getenv("SCRAPER_TIMEOUT", "120"))
MAX_REVIEWS = int(os.getenv("SCRAPER_MAX_REVIEWS", "100"))
MAX_RETRIES = int(os.getenv("SCRAPER_MAX_RETRIES", "5"))
MAX_PROVIDER_RUNTIME = int(os.getenv("SCRAPER_PROVIDER_RUNTIME", "60"))

ENABLE_SERPAPI = os.getenv("ENABLE_SERPAPI_SCRAPER", "true").lower() == "true"
ENABLE_PLAYWRIGHT = os.getenv("ENABLE_PLAYWRIGHT_FALLBACK", "true").lower() == "true"
ENABLE_CURL = os.getenv("ENABLE_CURL_SCRAPER", "true").lower() == "true"
ENABLE_CRAWL4AI = os.getenv("ENABLE_CRAWL4AI_SCRAPER", "true").lower() == "true"

# =========================================================
# PROXY
# =========================================================
PROXY_URL = ""
if PROXY_USERNAME and PROXY_PASSWORD and PROXY_SERVER:
    PROXY_URL = f"http://{PROXY_USERNAME}:{PROXY_PASSWORD}@{PROXY_SERVER}"

# =========================================================
# OPTIONAL IMPORTS
# =========================================================
REQUESTS_AVAILABLE = PLAYWRIGHT_AVAILABLE = STEALTH_AVAILABLE = False
BS4_AVAILABLE = SELECTOLAX_AVAILABLE = CURL_AVAILABLE = False
CRAWL4AI_AVAILABLE = FAKE_UA_AVAILABLE = False

try:
    import requests
    REQUESTS_AVAILABLE = True
except Exception as e:
    logger.warning(f"requests unavailable => {e}")

try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except Exception as e:
    logger.warning(f"BeautifulSoup unavailable => {e}")

try:
    from selectolax.parser import HTMLParser
    SELECTOLAX_AVAILABLE = True
except Exception as e:
    logger.warning(f"selectolax unavailable => {e}")

try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except Exception as e:
    logger.warning(f"playwright unavailable => {e}")

try:
    from playwright_stealth import stealth_async
    STEALTH_AVAILABLE = True
except Exception as e:
    logger.warning(f"playwright stealth unavailable => {e}")

try:
    from curl_cffi.requests import Session as CurlSession
    CURL_AVAILABLE = True
except Exception as e:
    logger.warning(f"curl_cffi unavailable => {e}")

try:
    from crawl4ai import AsyncWebCrawler
    CRAWL4AI_AVAILABLE = True
except Exception as e:
    logger.warning(f"crawl4ai unavailable => {e}")

try:
    from fake_useragent import UserAgent
    fake_ua = UserAgent()
    FAKE_UA_AVAILABLE = True
except Exception:
    fake_ua = None
    FAKE_UA_AVAILABLE = False

# =========================================================
# HELPERS
# =========================================================
def utc_now():
    return datetime.utcnow()


def get_user_agent() -> str:
    if FAKE_UA_AVAILABLE and fake_ua:
        try:
            return fake_ua.random
        except Exception:
            pass
    return (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    )


async def human_delay(minimum: float = 1.0, maximum: float = 3.0):
    await asyncio.sleep(random.uniform(minimum, maximum))


def maps_url(place_id: str) -> str:
    return f"https://www.google.com/maps/place/?q=place_id:{place_id}"


def generate_review_id(place_id: str, author: str, text: str) -> str:
    raw = f"{place_id}_{author}_{text[:200]}"
    return hashlib.sha256(raw.encode()).hexdigest()


def simple_sentiment(text: str) -> str:
    text = str(text).lower()
    positive_words = {"good", "great", "excellent", "awesome", "love", "perfect", "amazing"}
    negative_words = {"bad", "terrible", "worst", "awful", "poor", "horrible"}

    positive = sum(1 for word in positive_words if word in text)
    negative = sum(1 for word in negative_words if word in text)

    if positive > negative:
        return "positive"
    if negative > positive:
        return "negative"
    return "neutral"


def normalize_review(review: Dict[str, Any], place_id: str) -> Dict[str, Any]:
    review_text = str(
        review.get("review_text") or review.get("text") or review.get("content") or ""
    ).strip()

    if not review_text:
        return {}

    author = str(review.get("author", "Anonymous")).strip()
    rating = int(review.get("rating", 5) or 5)

    sentiment = simple_sentiment(review_text)

    return {
        "google_review_id": generate_review_id(place_id, author, review_text),
        "author": author,
        "author_name": author,
        "rating": rating,
        "review_text": review_text,
        "content": review_text,
        "text": review_text,
        "sentiment": sentiment,
        "sentiment_score": 0.85 if sentiment == "positive" else 0.15 if sentiment == "negative" else 0.50,
        "source": review.get("source", "Google"),
        "google_review_time": utc_now(),
        "scraped_at": utc_now(),
    }


def deduplicate_reviews(reviews: List[Dict]) -> List[Dict]:
    unique_reviews = []
    seen = set()
    for review in reviews:
        rid = review.get("google_review_id")
        if rid and rid not in seen:
            seen.add(rid)
            unique_reviews.append(review)
    return unique_reviews


# =========================================================
# SERPAPI
# =========================================================
@retry(stop=stop_after_attempt(MAX_RETRIES), wait=wait_random_exponential(min=2, max=15), reraise=True)
def serpapi_reviews(place_id: str) -> List[Dict]:
    logger.info("🚀 SERPAPI STARTED")
    if not ENABLE_SERPAPI or not SERPAPI_KEY:
        return []

    params = {
        "engine": "google_maps_reviews",
        "place_id": place_id,
        "api_key": SERPAPI_KEY,
        "hl": "en",
        "sort": "most_relevant"
    }

    response = requests.get(
        "https://serpapi.com/search.json",
        params=params,
        proxies={"http": PROXY_URL, "https": PROXY_URL} if PROXY_URL else None,
        headers={"User-Agent": get_user_agent()},
        timeout=SCRAPER_TIMEOUT
    )
    response.raise_for_status()
    data = response.json()

    raw_reviews = data.get("reviews", [])
    reviews = []

    for item in raw_reviews:
        review = normalize_review({
            "author": item.get("user", "Google User"),
            "rating": item.get("rating", 5),
            "review_text": item.get("snippet", ""),
            "source": "SERPAPI"
        }, place_id)
        if review:
            reviews.append(review)

    logger.info(f"✅ SERPAPI REVIEWS => {len(reviews)}")
    return reviews


# =========================================================
# PLAYWRIGHT (Most Reliable)
# =========================================================
@backoff.on_exception(backoff.expo, Exception, max_time=MAX_PROVIDER_RUNTIME)
async def playwright_reviews(place_id: str) -> List[Dict]:
    logger.info("🚀 PLAYWRIGHT STARTED")
    if not ENABLE_PLAYWRIGHT or not PLAYWRIGHT_AVAILABLE:
        return []

    reviews = []
    browser = None

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                proxy={
                    "server": f"http://{PROXY_SERVER}",
                    "username": PROXY_USERNAME,
                    "password": PROXY_PASSWORD
                } if PROXY_SERVER else None,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--disable-extensions",
                    "--disable-background-networking",
                    "--single-process"
                ]
            )

            context = await browser.new_context(
                user_agent=get_user_agent(),
                viewport={"width": 1920, "height": 1080},
                locale="en-US"
            )
            page = await context.new_page()

            if STEALTH_AVAILABLE:
                await stealth_async(page)

            await page.goto(maps_url(place_id), wait_until="domcontentloaded", timeout=90000)
            await human_delay(4, 7)

            # Click "More reviews" button
            try:
                await page.locator('button[jsaction*="pane.reviewChart.moreReviews"]').first.click(timeout=10000)
                await human_delay(3, 5)
            except:
                pass

            # Scroll to load reviews
            for _ in range(35):
                await page.evaluate("window.scrollBy(0, 1500)")
                await human_delay(0.6, 1.3)

            html = await page.content()
            soup = BeautifulSoup(html, "html.parser")

            # Multiple possible selectors (Google changes them often)
            selectors = [
                "div.jftiEf", "div[data-review-id]", ".wiI7pd",
                "div.MyEned", "div.section-review-content"
            ]

            review_blocks = []
            for selector in selectors:
                blocks = soup.select(selector)
                if blocks:
                    review_blocks.extend(blocks)
                    logger.info(f"✅ Playwright selector success: {selector} ({len(blocks)} blocks)")

            for block in review_blocks:
                try:
                    author = block.select_one(".d4r55, .fontTitleMedium")
                    rating = block.select_one("span.kvMYJc, .kvMYJc")
                    text = block.select_one(".wiI7pd, .fontBodyMedium")

                    author_name = author.get_text(strip=True) if author else "Anonymous"
                    review_text = text.get_text(strip=True) if text else ""

                    if rating and rating.get("aria-label"):
                        match = re.search(r"(\d\.\d|\d)", rating["aria-label"])
                        rating_val = int(float(match.group(1))) if match else 5
                    else:
                        rating_val = 5

                    review = normalize_review({
                        "author": author_name,
                        "rating": rating_val,
                        "review_text": review_text,
                        "source": "PLAYWRIGHT"
                    }, place_id)

                    if review:
                        reviews.append(review)
                except Exception as e:
                    continue

    except Exception as e:
        logger.error(f"❌ Playwright Error: {e}")
    finally:
        if browser:
            await browser.close()

    logger.info(f"✅ PLAYWRIGHT REVIEWS => {len(reviews)}")
    return reviews


# =========================================================
# CURL_CFFI
# =========================================================
@retry(stop=stop_after_attempt(MAX_RETRIES), wait=wait_random_exponential(min=2, max=12), reraise=True)
def curl_reviews(place_id: str) -> List[Dict]:
    logger.info("🚀 CURL_CFFI STARTED")
    if not ENABLE_CURL or not CURL_AVAILABLE:
        return []

    session = CurlSession()
    response = session.get(
        maps_url(place_id),
        impersonate="chrome124",
        proxies={"http": PROXY_URL, "https": PROXY_URL} if PROXY_URL else None,
        headers={
            "User-Agent": get_user_agent(),
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml"
        },
        timeout=SCRAPER_TIMEOUT
    )

    if not SELECTOLAX_AVAILABLE:
        return []

    parser = HTMLParser(response.text)
    nodes = parser.css(".wiI7pd, .jftiEf")

    reviews = []
    for node in nodes:
        review = normalize_review({
            "author": "Google User",
            "rating": 5,
            "review_text": node.text(),
            "source": "CURL_CFFI"
        }, place_id)
        if review:
            reviews.append(review)

    logger.info(f"✅ CURL REVIEWS => {len(reviews)}")
    return reviews


# =========================================================
# CRAWL4AI
# =========================================================
@backoff.on_exception(backoff.expo, Exception, max_time=MAX_PROVIDER_RUNTIME)
async def crawl4ai_reviews(place_id: str) -> List[Dict]:
    logger.info("🚀 CRAWL4AI STARTED")
    if not ENABLE_CRAWL4AI or not CRAWL4AI_AVAILABLE:
        return []

    reviews = []
    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(url=maps_url(place_id))
        html = getattr(result, "html", "")

        if BS4_AVAILABLE:
            soup = BeautifulSoup(html, "html.parser")
            blocks = soup.select(".wiI7pd, .jftiEf")

            for block in blocks:
                review = normalize_review({
                    "author": "Google User",
                    "rating": 5,
                    "review_text": block.get_text(strip=True),
                    "source": "CRAWL4AI"
                }, place_id)
                if review:
                    reviews.append(review)

    logger.info(f"✅ CRAWL4AI REVIEWS => {len(reviews)}")
    return reviews


# =========================================================
# MASTER SCRAPER
# =========================================================
async def scrape_google_reviews(place_id: str) -> List[Dict]:
    logger.info(f"🚀 MASTER SCRAPER STARTED => {place_id}")

    if not place_id:
        logger.error("❌ INVALID PLACE ID")
        return []

    all_reviews = []

    tasks = []
    if ENABLE_SERPAPI:
        tasks.append(asyncio.to_thread(serpapi_reviews, place_id))
    if ENABLE_PLAYWRIGHT:
        tasks.append(playwright_reviews(place_id))
    if ENABLE_CURL:
        tasks.append(asyncio.to_thread(curl_reviews, place_id))
    if ENABLE_CRAWL4AI:
        tasks.append(crawl4ai_reviews(place_id))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    for result in results:
        if isinstance(result, Exception):
            logger.error(f"Provider failed: {result}")
            continue
        if result:
            all_reviews.extend(result)

    all_reviews = deduplicate_reviews(all_reviews)
    if MAX_REVIEWS > 0:
        all_reviews = all_reviews[:MAX_REVIEWS]

    logger.info(f"✅ FINAL REVIEWS => {len(all_reviews)} (Place ID: {place_id})")
    return all_reviews


# =========================================================
# TEST
# =========================================================
if __name__ == "__main__":
    async def main():
        place_id = "ChIJN1t_tDeuEmsRUsoyG83frY4"  # Sydney Opera House
        reviews = await scrape_google_reviews(place_id)
        print(json.dumps(reviews[:5], indent=4, default=str))

    asyncio.run(main())
