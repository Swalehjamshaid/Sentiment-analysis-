# =========================================================
# FILE: app/scraper.py
# TRUSTLYTICS AI - POWERFUL ASYNC GOOGLE REVIEWS SCRAPER
# =========================================================

import os
import re
import json
import asyncio
import logging
import traceback
import random
import hashlib
import time

from datetime import datetime
from typing import List, Dict, Any, Callable

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

# Each provider retries until this many seconds have passed.
PROVIDER_RETRY_SECONDS = int(
    os.getenv("SCRAPER_PROVIDER_RETRY_SECONDS", "30")
)

SCRAPER_TIMEOUT = int(os.getenv("SCRAPER_TIMEOUT", "20"))

ENABLE_SERPAPI = os.getenv("ENABLE_SERPAPI_SCRAPER", "true").lower() == "true"
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

def utc_now() -> datetime:
    return datetime.utcnow()


def get_user_agent() -> str:
    if FAKE_UA_AVAILABLE and fake_ua:
        try:
            return fake_ua.random
        except Exception:
            pass

    versions = ["120", "121", "122", "123", "124", "125", "126"]
    version = random.choice(versions)

    return (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        f"Chrome/{version}.0.0.0 Safari/537.36"
    )


async def human_delay(
    minimum: float = 0.8,
    maximum: float = 2.0,
):
    await asyncio.sleep(random.uniform(minimum, maximum))


async def retry_async_for_seconds(
    name: str,
    func: Callable,
    *args,
    retry_seconds: int = PROVIDER_RETRY_SECONDS,
    **kwargs,
):
    deadline = time.monotonic() + retry_seconds
    attempt = 0
    last_error = None

    while time.monotonic() < deadline:
        attempt += 1

        try:
            remaining = max(0, int(deadline - time.monotonic()))

            logger.info(
                f"{name} attempt {attempt}, remaining {remaining}s"
            )

            result = await func(*args, **kwargs)

            if result:
                logger.info(
                    f"{name} success on attempt {attempt} => {len(result)} reviews"
                )

                return result

            last_error = "empty result"

            await asyncio.sleep(
                min(5, max(1, retry_seconds / 10)) + random.uniform(0.2, 1.0)
            )

        except Exception as e:
            last_error = e

            logger.warning(
                f"{name} attempt {attempt} failed => {e}"
            )

            await asyncio.sleep(
                min(5, attempt * 1.5) + random.uniform(0.2, 1.0)
            )

    logger.error(
        f"{name} stopped after {retry_seconds}s => {last_error}"
    )

    return []


async def retry_thread_for_seconds(
    name: str,
    func: Callable,
    *args,
    retry_seconds: int = PROVIDER_RETRY_SECONDS,
    **kwargs,
):
    deadline = time.monotonic() + retry_seconds
    attempt = 0
    last_error = None

    while time.monotonic() < deadline:
        attempt += 1

        try:
            remaining = max(0, int(deadline - time.monotonic()))

            logger.info(
                f"{name} attempt {attempt}, remaining {remaining}s"
            )

            result = await asyncio.to_thread(
                func,
                *args,
                **kwargs,
            )

            if result:
                logger.info(
                    f"{name} success on attempt {attempt} => {len(result)} reviews"
                )

                return result

            last_error = "empty result"

            await asyncio.sleep(
                min(5, max(1, retry_seconds / 10)) + random.uniform(0.2, 1.0)
            )

        except Exception as e:
            last_error = e

            logger.warning(
                f"{name} attempt {attempt} failed => {e}"
            )

            await asyncio.sleep(
                min(5, attempt * 1.5) + random.uniform(0.2, 1.0)
            )

    logger.error(
        f"{name} stopped after {retry_seconds}s => {last_error}"
    )

    return []


def safe_str(value: Any, default: str = "") -> str:
    if value is None:
        return default

    return str(value).strip()


def safe_rating(value: Any, default: int = 5) -> int:
    try:
        if isinstance(value, str):
            match = re.search(r"([1-5](?:\.\d+)?)", value)
            value = match.group(1) if match else default

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
    raw = f"{place_id}:{author}:{review_text}".lower().strip()

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()


def parse_rating_from_text(text: str) -> int:
    text = safe_str(text)

    match = re.search(r"([1-5])", text)

    if not match:
        return 5

    return safe_rating(match.group(1), 5)


def parse_review_time(value: Any) -> Any:
    if isinstance(value, datetime):
        return value

    value = safe_str(value)

    if not value:
        return utc_now()

    return value


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
        "professional",
        "quick",
        "fast",
        "happy",
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
        "avoid",
        "broken",
        "angry",
    ]

    positive_score = sum(1 for word in positive_words if word in text)
    negative_score = sum(1 for word in negative_words if word in text)

    if positive_score > negative_score:
        return "positive"

    if negative_score > positive_score:
        return "negative"

    return "neutral"


def sentiment_score_from_label(label: str) -> float:
    if label == "positive":
        return 0.85

    if label == "negative":
        return 0.15

    return 0.5


def normalize_review(
    review: Dict[str, Any],
    place_id: str = "",
) -> Dict[str, Any]:
    review_text = safe_str(
        review.get("review_text")
        or review.get("text")
        or review.get("content")
        or review.get("snippet")
        or review.get("description")
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

    sentiment = safe_str(
        review.get("sentiment"),
        simple_sentiment(review_text),
    )

    sentiment_score = review.get("sentiment_score")

    if sentiment_score is None:
        sentiment_score = sentiment_score_from_label(sentiment)

    source = safe_str(
        review.get("source"),
        "Google",
    )

    google_review_time = parse_review_time(
        review.get("google_review_time")
        or review.get("review_date")
        or review.get("date")
        or review.get("time")
    )

    return {
        "google_review_id": review_id,
        "author": author,
        "author_name": author,
        "rating": rating,
        "review_text": review_text,
        "content": review_text,
        "text": review_text,
        "sentiment": sentiment,
        "sentiment_score": sentiment_score,
        "source": source,
        "google_review_time": google_review_time,
        "review_date": google_review_time,
        "scraped_at": utc_now(),
        "place_id": place_id,
    }


def deduplicate_reviews(
    reviews: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    unique_reviews = []
    seen = set()

    for review in reviews:
        review_text = safe_str(review.get("review_text"))
        author = safe_str(review.get("author"))
        review_id = safe_str(review.get("google_review_id"))

        if not review_text:
            continue

        key = review_id or f"{author.lower()}:{review_text.lower()}"

        if key in seen:
            continue

        seen.add(key)
        unique_reviews.append(review)

    return unique_reviews


def google_maps_url(place_id: str) -> str:
    return f"https://www.google.com/maps/place/?q=place_id:{place_id}"


def frontend_payload(
    reviews: List[Dict[str, Any]],
    place_id: str,
    provider_status: List[Dict[str, Any]],
) -> Dict[str, Any]:
    return {
        "success": True,
        "place_id": place_id,
        "total_reviews": len(reviews),
        "reviews": reviews,
        "provider_status": provider_status,
        "scraped_at": utc_now().isoformat(),
    }

# =========================================================
# SERPAPI SCRAPER
# =========================================================

def serpapi_reviews(
    place_id: str,
) -> List[Dict[str, Any]]:
    logger.info("SERPAPI STARTED")

    reviews = []

    if not ENABLE_SERPAPI:
        logger.info("SERPAPI disabled")
        return reviews

    if not SERPAPI_KEY:
        logger.warning("SERPAPI_KEY missing")
        return reviews

    if not REQUESTS_AVAILABLE:
        logger.warning("requests package missing")
        return reviews

    params = {
        "engine": "google_maps_reviews",
        "place_id": place_id,
        "api_key": SERPAPI_KEY,
        "hl": "en",
    }

    while len(reviews) < MAX_REVIEWS:
        response = requests.get(
            "https://serpapi.com/search.json",
            params=params,
            timeout=SCRAPER_TIMEOUT,
        )

        response.raise_for_status()

        data = response.json()

        raw_reviews = data.get("reviews", []) or []

        for item in raw_reviews:
            review = normalize_review(
                {
                    "google_review_id": item.get("review_id") or item.get("id"),
                    "author": (
                        item.get("user", {}).get("name")
                        if isinstance(item.get("user"), dict)
                        else item.get("user")
                    ) or item.get("name"),
                    "rating": item.get("rating"),
                    "review_text": item.get("snippet") or item.get("text"),
                    "google_review_time": item.get("date"),
                    "source": "SERPAPI",
                },
                place_id=place_id,
            )

            if review:
                reviews.append(review)

        next_page_token = (
            data.get("serpapi_pagination", {}).get("next_page_token")
            or data.get("search_metadata", {}).get("next_page_token")
        )

        if not next_page_token:
            break

        params["next_page_token"] = next_page_token

    logger.info(f"SERPAPI REVIEWS => {len(reviews)}")

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
    context = None

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
                timezone_id="UTC",
            )

            page = await context.new_page()

            if STEALTH_AVAILABLE:
                try:
                    await stealth_async(page)
                except Exception as stealth_error:
                    logger.warning(f"stealth failed => {stealth_error}")

            await page.goto(
                google_maps_url(place_id),
                timeout=90000,
                wait_until="domcontentloaded",
            )

            await human_delay(3, 5)

            for selector in [
                'button:has-text("Accept all")',
                'button:has-text("I agree")',
                'button:has-text("Accept")',
            ]:
                try:
                    button = page.locator(selector).first()

                    if await button.count() > 0:
                        await button.click(timeout=3000)
                        await human_delay(1, 2)
                        break
                except Exception:
                    continue

            for selector in [
                'button[jsaction*="pane.reviewChart.moreReviews"]',
                'button[aria-label*="reviews"]',
                'button[aria-label*="Reviews"]',
                'button:has-text("reviews")',
                'button:has-text("Reviews")',
            ]:
                try:
                    button = page.locator(selector).first()

                    if await button.count() > 0:
                        await button.click(timeout=7000)
                        await human_delay(2, 4)
                        break
                except Exception:
                    continue

            for _ in range(40):
                scrolled = False

                for selector in [
                    'div[role="main"]',
                    'div[aria-label*="Reviews"]',
                    'div.m6QErb',
                ]:
                    try:
                        target = page.locator(selector).last()

                        if await target.count() > 0:
                            await target.evaluate(
                                "(el) => el.scrollTop = el.scrollHeight"
                            )
                            scrolled = True
                            break
                    except Exception:
                        continue

                if not scrolled:
                    await page.mouse.wheel(0, 9000)

                await human_delay(0.35, 0.9)

            html_content = await page.content()

            soup = BeautifulSoup(html_content, "html.parser")

            review_blocks = soup.select("div.jftiEf, div[data-review-id]")

            logger.info(f"PLAYWRIGHT BLOCKS => {len(review_blocks)}")

            for block in review_blocks:
                author = "Anonymous"
                rating = 5
                review_text = ""

                author_element = block.select_one(".d4r55")

                if author_element:
                    author = author_element.get_text(strip=True)

                review_element = block.select_one(".wiI7pd")

                if review_element:
                    review_text = review_element.get_text(" ", strip=True)

                rating_element = block.select_one("span.kvMYJc")

                if rating_element:
                    rating = parse_rating_from_text(
                        rating_element.get("aria-label", "")
                    )

                review = normalize_review(
                    {
                        "google_review_id": block.get("data-review-id") or "",
                        "author": author,
                        "rating": rating,
                        "review_text": review_text,
                        "source": "PLAYWRIGHT",
                    },
                    place_id=place_id,
                )

                if review:
                    reviews.append(review)

            await context.close()
            await browser.close()

    except Exception:
        try:
            if context:
                await context.close()
        except Exception:
            pass

        try:
            if browser:
                await browser.close()
        except Exception:
            pass

        raise

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
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
        timeout=SCRAPER_TIMEOUT,
    )

    parser = HTMLParser(response.text)

    nodes = parser.css(".wiI7pd")

    logger.info(f"CURL NODES => {len(nodes)}")

    for node in nodes:
        review = normalize_review(
            {
                "author": "Google User",
                "rating": 5,
                "review_text": safe_str(node.text()),
                "source": "CURL_CFFI",
            },
            place_id=place_id,
        )

        if review:
            reviews.append(review)

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

    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(
            url=google_maps_url(place_id)
        )

        html_content = getattr(result, "html", "") or ""

        soup = BeautifulSoup(html_content, "html.parser")

        elements = soup.select(".wiI7pd")

        logger.info(f"CRAWL4AI ELEMENTS => {len(elements)}")

        for element in elements:
            review = normalize_review(
                {
                    "author": "Google User",
                    "rating": 5,
                    "review_text": safe_str(
                        element.get_text(" ", strip=True)
                    ),
                    "source": "CRAWL4AI",
                },
                place_id=place_id,
            )

            if review:
                reviews.append(review)

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
    provider_status = []

    async def run_provider(
        name: str,
        runner: Callable,
    ):
        started_at = utc_now()

        reviews = await runner()

        provider_status.append({
            "provider": name,
            "success": bool(reviews),
            "reviews": len(reviews),
            "retry_seconds": PROVIDER_RETRY_SECONDS,
            "started_at": started_at.isoformat(),
            "finished_at": utc_now().isoformat(),
        })

        return reviews

    serp_reviews = await run_provider(
        "SERPAPI",
        lambda: retry_thread_for_seconds(
            "SERPAPI",
            serpapi_reviews,
            place_id,
        ),
    )

    all_reviews.extend(serp_reviews)
    all_reviews = deduplicate_reviews(all_reviews)

    logger.info(f"AFTER SERPAPI => {len(all_reviews)}")

    if len(all_reviews) < MAX_REVIEWS:
        playwright_result = await run_provider(
            "PLAYWRIGHT",
            lambda: retry_async_for_seconds(
                "PLAYWRIGHT",
                playwright_reviews,
                place_id,
            ),
        )

        all_reviews.extend(playwright_result)
        all_reviews = deduplicate_reviews(all_reviews)

        logger.info(f"AFTER PLAYWRIGHT => {len(all_reviews)}")

    if len(all_reviews) < MAX_REVIEWS:
        curl_result = await run_provider(
            "CURL_CFFI",
            lambda: retry_thread_for_seconds(
                "CURL_CFFI",
                curl_reviews,
                place_id,
            ),
        )

        all_reviews.extend(curl_result)
        all_reviews = deduplicate_reviews(all_reviews)

        logger.info(f"AFTER CURL => {len(all_reviews)}")

    if len(all_reviews) < MAX_REVIEWS:
        crawl_result = await run_provider(
            "CRAWL4AI",
            lambda: retry_async_for_seconds(
                "CRAWL4AI",
                crawl4ai_reviews,
                place_id,
            ),
        )

        all_reviews.extend(crawl_result)
        all_reviews = deduplicate_reviews(all_reviews)

        logger.info(f"AFTER CRAWL4AI => {len(all_reviews)}")

    all_reviews = deduplicate_reviews(all_reviews)

    if MAX_REVIEWS > 0:
        all_reviews = all_reviews[:MAX_REVIEWS]

    for review in all_reviews:
        review["scraper_status"] = provider_status

    logger.info(f"FINAL UNIQUE REVIEWS => {len(all_reviews)}")

    return all_reviews


async def scrape_google_reviews_with_meta(
    place_id: str,
) -> Dict[str, Any]:
    reviews = await scrape_google_reviews(place_id)

    provider_status = []

    if reviews:
        provider_status = reviews[0].get("scraper_status", [])

    return frontend_payload(
        reviews=reviews,
        place_id=place_id,
        provider_status=provider_status,
    )

# =========================================================
# TEST
# =========================================================

if __name__ == "__main__":

    async def main():
        place_id = os.getenv(
            "TEST_PLACE_ID",
            "ChIJN1t_tDeuEmsRUsoyG83frY4",
        )

        payload = await scrape_google_reviews_with_meta(place_id)

        print(
            json.dumps(
                payload,
                indent=4,
                default=str,
            )
        )

    asyncio.run(main())

# =========================================================
# END OF FILE
# =========================================================
