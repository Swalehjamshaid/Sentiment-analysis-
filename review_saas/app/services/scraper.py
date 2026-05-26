# =========================================================
# FILE: app/scraper.py
# TRUSTLYTICS AI - SAFE ASYNC GOOGLE REVIEWS SCRAPER
# =========================================================

import os
import re
import json
import asyncio
import logging
import traceback
import random
import hashlib

from datetime import datetime
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# =========================================================
# CONFIG
# =========================================================

SERPAPI_KEY = os.getenv("SERPAPI_KEY", "").strip()

PROXY_USERNAME = os.getenv("PROXY_USERNAME", "").strip()
PROXY_PASSWORD = os.getenv("PROXY_PASSWORD", "").strip()
PROXY_SERVER = os.getenv("PROXY_SERVER", "").strip()

MAX_REVIEWS = int(os.getenv("SCRAPER_MAX_REVIEWS", "100"))
ENABLE_PLAYWRIGHT = os.getenv("ENABLE_PLAYWRIGHT_SCRAPER", "true").lower() == "true"
ENABLE_CURL = os.getenv("ENABLE_CURL_SCRAPER", "true").lower() == "true"
ENABLE_CRAWL4AI = os.getenv("ENABLE_CRAWL4AI_SCRAPER", "false").lower() == "true"

PROXY_URL = ""

if PROXY_USERNAME and PROXY_PASSWORD and PROXY_SERVER:
    PROXY_URL = f"http://{PROXY_USERNAME}:{PROXY_PASSWORD}@{PROXY_SERVER}"

# =========================================================
# OPTIONAL IMPORTS
# =========================================================

REQUESTS_AVAILABLE = False
PLAYWRIGHT_AVAILABLE = False
STEALTH_AVAILABLE = False
BS4_AVAILABLE = False
SELECTOLAX_AVAILABLE = False
CURL_CFFI_AVAILABLE = False
CRAWL4AI_AVAILABLE = False
FAKE_UA_AVAILABLE = False

try:
    import requests

    REQUESTS_AVAILABLE = True
except Exception as e:
    logger.warning(f"requests unavailable => {e}")

try:
    from bs4 import BeautifulSoup

    BS4_AVAILABLE = True
except Exception as e:
    logger.warning(f"bs4 unavailable => {e}")

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
    logger.warning(f"playwright_stealth unavailable => {e}")

try:
    from curl_cffi.requests import Session as CurlSession

    CURL_CFFI_AVAILABLE = True
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
except Exception as e:
    logger.warning(f"fake_useragent unavailable => {e}")
    fake_ua = None

# =========================================================
# HELPERS
# =========================================================

def get_user_agent() -> str:
    if FAKE_UA_AVAILABLE and fake_ua:
        try:
            return fake_ua.random
        except Exception:
            pass

    return (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )


async def human_delay(
    minimum: float = 0.8,
    maximum: float = 2.0,
):
    await asyncio.sleep(random.uniform(minimum, maximum))


def safe_str(value: Any, default: str = "") -> str:
    if value is None:
        return default

    return str(value).strip()


def safe_rating(value: Any, default: int = 5) -> int:
    try:
        rating = int(float(value))
    except Exception:
        rating = default

    if rating < 1:
        rating = 1

    if rating > 5:
        rating = 5

    return rating


def stable_review_id(
    place_id: str,
    author: str,
    review_text: str,
) -> str:
    raw = f"{place_id}:{author}:{review_text}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def parse_rating_from_text(text: str) -> int:
    text = safe_str(text)

    match = re.search(r"([1-5])", text)

    if not match:
        return 5

    return safe_rating(match.group(1), 5)


def simple_sentiment(text: str) -> str:
    text = safe_str(text).lower()

    positive_words = [
        "good",
        "great",
        "excellent",
        "perfect",
        "love",
        "amazing",
        "awesome",
        "best",
        "fantastic",
        "nice",
        "friendly",
        "clean",
        "helpful",
        "recommended",
    ]

    negative_words = [
        "bad",
        "worst",
        "terrible",
        "awful",
        "hate",
        "poor",
        "dirty",
        "rude",
        "slow",
        "late",
        "expensive",
        "disappointed",
        "unprofessional",
    ]

    positive_score = sum(1 for word in positive_words if word in text)
    negative_score = sum(1 for word in negative_words if word in text)

    if positive_score > negative_score:
        return "positive"

    if negative_score > positive_score:
        return "negative"

    return "neutral"


def normalize_review(
    review: Dict[str, Any],
    place_id: str = "",
) -> Dict[str, Any]:
    review_text = safe_str(
        review.get("review_text")
        or review.get("text")
        or review.get("content")
        or review.get("snippet")
    )

    if not review_text:
        return {}

    author = safe_str(
        review.get("author")
        or review.get("author_name")
        or review.get("user")
        or review.get("name"),
        "Anonymous",
    )

    if not author:
        author = "Anonymous"

    rating = safe_rating(
        review.get("rating")
        or review.get("stars")
        or review.get("score"),
        5,
    )

    review_id = safe_str(
        review.get("google_review_id")
        or review.get("review_id")
        or review.get("id")
    )

    if not review_id:
        review_id = stable_review_id(
            place_id=place_id,
            author=author,
            review_text=review_text,
        )

    return {
        "google_review_id": review_id,
        "author": author,
        "author_name": author,
        "rating": rating,
        "review_text": review_text,
        "content": review_text,
        "text": review_text,
        "sentiment": simple_sentiment(review_text),
        "sentiment_score": 0.5,
        "source": safe_str(review.get("source"), "Google"),
        "google_review_time": review.get("google_review_time") or datetime.utcnow(),
        "review_date": review.get("review_date") or datetime.utcnow(),
    }


def deduplicate_reviews(
    reviews: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    unique_reviews = []
    seen = set()

    for review in reviews:
        review_text = safe_str(review.get("review_text"))
        author = safe_str(review.get("author"))

        if not review_text:
            continue

        key = f"{author.lower()}:{review_text.lower()}"

        if key in seen:
            continue

        seen.add(key)
        unique_reviews.append(review)

    return unique_reviews


def google_maps_url(place_id: str) -> str:
    return f"https://www.google.com/maps/place/?q=place_id:{place_id}"

# =========================================================
# SERPAPI SCRAPER
# =========================================================

def serpapi_reviews(
    place_id: str,
) -> List[Dict[str, Any]]:
    logger.info("SERPAPI STARTED")

    reviews = []

    if not SERPAPI_KEY:
        logger.warning("SERPAPI_KEY missing")
        return reviews

    if not REQUESTS_AVAILABLE:
        logger.warning("requests package missing")
        return reviews

    try:
        params = {
            "engine": "google_maps_reviews",
            "place_id": place_id,
            "api_key": SERPAPI_KEY,
            "hl": "en",
        }

        response = requests.get(
            "https://serpapi.com/search.json",
            params=params,
            timeout=60,
        )

        response.raise_for_status()

        data = response.json()

        raw_reviews = data.get("reviews", [])

        for item in raw_reviews:
            review = normalize_review(
                {
                    "google_review_id": item.get("review_id") or item.get("id"),
                    "author": item.get("user") or item.get("name"),
                    "rating": item.get("rating"),
                    "review_text": item.get("snippet") or item.get("text"),
                    "google_review_time": item.get("date"),
                    "source": "SERPAPI",
                },
                place_id=place_id,
            )

            if review:
                reviews.append(review)

        logger.info(f"SERPAPI REVIEWS => {len(reviews)}")

    except Exception as e:
        logger.error(f"SERPAPI ERROR => {e}")
        logger.error(traceback.format_exc())

    return reviews

# =========================================================
# PLAYWRIGHT SCRAPER
# =========================================================

async def playwright_reviews(
    place_id: str,
) -> List[Dict[str, Any]]:
    logger.info("PLAYWRIGHT STARTED")

    reviews = []

    if not ENABLE_PLAYWRIGHT:
        logger.info("PLAYWRIGHT disabled")
        return reviews

    if not PLAYWRIGHT_AVAILABLE:
        logger.warning("playwright package missing")
        return reviews

    if not BS4_AVAILABLE:
        logger.warning("bs4 package missing")
        return reviews

    browser = None

    try:
        async with async_playwright() as p:
            launch_options = {
                "headless": True,
                "args": [
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-infobars",
                    "--window-size=1920,1080",
                ],
            }

            if PROXY_SERVER:
                launch_options["proxy"] = {
                    "server": f"http://{PROXY_SERVER}",
                }

                if PROXY_USERNAME and PROXY_PASSWORD:
                    launch_options["proxy"]["username"] = PROXY_USERNAME
                    launch_options["proxy"]["password"] = PROXY_PASSWORD

            browser = await p.chromium.launch(**launch_options)

            context = await browser.new_context(
                user_agent=get_user_agent(),
                viewport={
                    "width": 1920,
                    "height": 1080,
                },
                locale="en-US",
            )

            page = await context.new_page()

            if STEALTH_AVAILABLE:
                try:
                    await stealth_async(page)
                except Exception as stealth_error:
                    logger.warning(f"stealth failed => {stealth_error}")

            url = google_maps_url(place_id)

            logger.info(f"OPENING => {url}")

            await page.goto(
                url,
                timeout=90000,
                wait_until="domcontentloaded",
            )

            await human_delay(3, 5)

            review_button_selectors = [
                'button[jsaction*="pane.reviewChart.moreReviews"]',
                'button[aria-label*="reviews"]',
                'button:has-text("reviews")',
                'button:has-text("Reviews")',
            ]

            for selector in review_button_selectors:
                try:
                    button = page.locator(selector).first()

                    if await button.count() > 0:
                        await button.click(timeout=5000)
                        logger.info(f"review button clicked => {selector}")
                        await human_delay(2, 4)
                        break

                except Exception:
                    continue

            for _ in range(25):
                await page.mouse.wheel(0, 8000)
                await human_delay(0.5, 1.2)

            html_content = await page.content()

            soup = BeautifulSoup(html_content, "html.parser")

            review_blocks = soup.select("div.jftiEf")

            logger.info(f"PLAYWRIGHT BLOCKS => {len(review_blocks)}")

            for block in review_blocks:
                try:
                    author = "Anonymous"
                    rating = 5
                    review_text = ""

                    author_element = block.select_one(".d4r55")

                    if author_element:
                        author = author_element.get_text(strip=True)

                    review_element = block.select_one(".wiI7pd")

                    if review_element:
                        review_text = review_element.get_text(strip=True)

                    rating_element = block.select_one("span.kvMYJc")

                    if rating_element:
                        rating = parse_rating_from_text(
                            rating_element.get("aria-label", "")
                        )

                    review = normalize_review(
                        {
                            "author": author,
                            "rating": rating,
                            "review_text": review_text,
                            "source": "PLAYWRIGHT",
                        },
                        place_id=place_id,
                    )

                    if review:
                        reviews.append(review)

                except Exception as parse_error:
                    logger.error(f"PLAYWRIGHT PARSE ERROR => {parse_error}")

            await context.close()
            await browser.close()

    except Exception as e:
        logger.error(f"PLAYWRIGHT ERROR => {e}")
        logger.error(traceback.format_exc())

        try:
            if browser:
                await browser.close()
        except Exception:
            pass

    logger.info(f"PLAYWRIGHT REVIEWS => {len(reviews)}")

    return reviews

# =========================================================
# CURL_CFFI SCRAPER
# =========================================================

def curl_reviews(
    place_id: str,
) -> List[Dict[str, Any]]:
    logger.info("CURL_CFFI STARTED")

    reviews = []

    if not ENABLE_CURL:
        logger.info("CURL disabled")
        return reviews

    if not CURL_CFFI_AVAILABLE:
        logger.warning("curl_cffi package missing")
        return reviews

    if not SELECTOLAX_AVAILABLE:
        logger.warning("selectolax package missing")
        return reviews

    try:
        session = CurlSession()

        proxies = None

        if PROXY_URL:
            proxies = {
                "http": PROXY_URL,
                "https": PROXY_URL,
            }

        response = session.get(
            google_maps_url(place_id),
            impersonate="chrome124",
            proxies=proxies,
            headers={
                "User-Agent": get_user_agent(),
                "Accept-Language": "en-US,en;q=0.9",
            },
            timeout=60,
        )

        parser = HTMLParser(response.text)

        nodes = parser.css(".wiI7pd")

        logger.info(f"CURL NODES => {len(nodes)}")

        for node in nodes:
            review_text = safe_str(node.text())

            review = normalize_review(
                {
                    "author": "Google User",
                    "rating": 5,
                    "review_text": review_text,
                    "source": "CURL_CFFI",
                },
                place_id=place_id,
            )

            if review:
                reviews.append(review)

    except Exception as e:
        logger.error(f"CURL ERROR => {e}")
        logger.error(traceback.format_exc())

    logger.info(f"CURL REVIEWS => {len(reviews)}")

    return reviews

# =========================================================
# CRAWL4AI SCRAPER
# =========================================================

async def crawl4ai_reviews(
    place_id: str,
) -> List[Dict[str, Any]]:
    logger.info("CRAWL4AI STARTED")

    reviews = []

    if not ENABLE_CRAWL4AI:
        logger.info("CRAWL4AI disabled")
        return reviews

    if not CRAWL4AI_AVAILABLE:
        logger.warning("crawl4ai package missing")
        return reviews

    if not BS4_AVAILABLE:
        logger.warning("bs4 package missing")
        return reviews

    try:
        async with AsyncWebCrawler() as crawler:
            result = await crawler.arun(
                url=google_maps_url(place_id)
            )

            html_content = getattr(result, "html", "") or ""

            soup = BeautifulSoup(html_content, "html.parser")

            elements = soup.select(".wiI7pd")

            logger.info(f"CRAWL4AI ELEMENTS => {len(elements)}")

            for element in elements:
                review_text = safe_str(element.get_text(strip=True))

                review = normalize_review(
                    {
                        "author": "Google User",
                        "rating": 5,
                        "review_text": review_text,
                        "source": "CRAWL4AI",
                    },
                    place_id=place_id,
                )

                if review:
                    reviews.append(review)

    except Exception as e:
        logger.error(f"CRAWL4AI ERROR => {e}")
        logger.error(traceback.format_exc())

    logger.info(f"CRAWL4AI REVIEWS => {len(reviews)}")

    return reviews

# =========================================================
# MASTER SCRAPER
# =========================================================

async def scrape_google_reviews(
    place_id: str,
) -> List[Dict[str, Any]]:
    logger.info(f"MASTER SCRAPER STARTED => {place_id}")

    place_id = safe_str(place_id)

    if not place_id:
        logger.warning("place_id missing")
        return []

    all_reviews = []

    try:
        serp_reviews = await asyncio.to_thread(
            serpapi_reviews,
            place_id,
        )

        all_reviews.extend(serp_reviews)

        logger.info(f"AFTER SERPAPI => {len(all_reviews)}")

        if len(all_reviews) < MAX_REVIEWS:
            playwright_result = await playwright_reviews(place_id)
            all_reviews.extend(playwright_result)

            logger.info(f"AFTER PLAYWRIGHT => {len(all_reviews)}")

        if len(all_reviews) < MAX_REVIEWS:
            curl_result = await asyncio.to_thread(
                curl_reviews,
                place_id,
            )

            all_reviews.extend(curl_result)

            logger.info(f"AFTER CURL => {len(all_reviews)}")

        if len(all_reviews) < MAX_REVIEWS:
            crawl_result = await crawl4ai_reviews(place_id)
            all_reviews.extend(crawl_result)

            logger.info(f"AFTER CRAWL4AI => {len(all_reviews)}")

        all_reviews = deduplicate_reviews(all_reviews)

        if MAX_REVIEWS > 0:
            all_reviews = all_reviews[:MAX_REVIEWS]

        logger.info(f"FINAL UNIQUE REVIEWS => {len(all_reviews)}")

        return all_reviews

    except Exception as e:
        logger.error(f"MASTER SCRAPER ERROR => {e}")
        logger.error(traceback.format_exc())

        return []

# =========================================================
# TEST
# =========================================================

if __name__ == "__main__":

    async def main():
        place_id = os.getenv(
            "TEST_PLACE_ID",
            "ChIJN1t_tDeuEmsRUsoyG83frY4",
        )

        reviews = await scrape_google_reviews(place_id)

        print(
            json.dumps(
                reviews[:5],
                indent=4,
                default=str,
            )
        )

    asyncio.run(main())

# =========================================================
# END OF FILE
# =========================================================
