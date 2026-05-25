# ==========================================================
# scraper.py
# ENTERPRISE GOOGLE REVIEW SCRAPER
# FULL BACKWARD COMPATIBILITY VERSION
# ==========================================================

import os
import re
import gc
import json
import random
import asyncio
import logging

from bs4 import BeautifulSoup
from fake_useragent import UserAgent

from tenacity import (
    retry,
    stop_after_attempt,
    wait_random_exponential,
)

from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

from crawl4ai import AsyncWebCrawler

from curl_cffi import requests

# ==========================================================
# LOGGING
# ==========================================================

logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)

# ==========================================================
# ENVIRONMENT
# ==========================================================

SERPAPI_KEY = os.getenv("SERPAPI_KEY", "")

PROXY_SERVER = os.getenv("PROXY_SERVER", "")
PROXY_USERNAME = os.getenv("PROXY_USERNAME", "")
PROXY_PASSWORD = os.getenv("PROXY_PASSWORD", "")

HEADLESS = True

REQUEST_TIMEOUT = 180

PLAYWRIGHT_TIMEOUT = 120000

MAX_SCROLLS = 60

# ==========================================================
# USER AGENT
# ==========================================================

ua = UserAgent()

def get_user_agent():

    try:
        return ua.chrome

    except Exception:

        return (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0 Safari/537.36"
        )

# ==========================================================
# HELPERS
# ==========================================================

def clean_text(text):

    if not text:
        return ""

    text = str(text)

    text = text.replace("\n", " ")

    text = re.sub(r"\s+", " ", text)

    return text.strip()

def create_review_id(author, text):

    base = f"{author}_{text[:120]}"

    return str(abs(hash(base)))

def normalize_review(
    review,
    existing_ids=None,
    seen=None,
):

    existing_ids = existing_ids or set()

    seen = seen or set()

    author = clean_text(review.get("author", "Anonymous"))

    text = clean_text(review.get("text", ""))

    rating = review.get("rating", 5)

    date = clean_text(review.get("date", ""))

    if not text:
        return None

    review_id = create_review_id(author, text)

    if review_id in existing_ids:
        return None

    if review_id in seen:
        return None

    seen.add(review_id)

    return {
        "review_id": review_id,
        "author": author,
        "text": text,
        "rating": rating,
        "date": date,
    }

# ==========================================================
# SERPAPI FALLBACK
# ==========================================================

async def serpapi_reviews(
    place_id,
    existing_ids=None,
    target_limit=50,
):

    if not SERPAPI_KEY:

        logger.warning("SERPAPI KEY MISSING")

        return []

    logger.info("LEVEL 3 => SERPAPI")

    reviews = []

    seen = set()

    try:

        params = {
            "engine": "google_maps_reviews",
            "place_id": place_id,
            "api_key": SERPAPI_KEY,
        }

        response = requests.get(
            "https://serpapi.com/search.json",
            params=params,
            timeout=REQUEST_TIMEOUT,
        )

        data = response.json()

        items = data.get("reviews", [])

        logger.info(f"SERPAPI REVIEWS => {len(items)}")

        for item in items:

            normalized = normalize_review(
                {
                    "author": item.get("user", {}).get("name", ""),
                    "text": item.get("snippet", ""),
                    "rating": item.get("rating", 5),
                    "date": item.get("date", ""),
                },
                existing_ids,
                seen,
            )

            if not normalized:
                continue

            reviews.append(normalized)

            if len(reviews) >= target_limit:
                break

        return reviews

    except Exception as e:

        logger.exception(f"SERPAPI FAILED => {e}")

        return []

# ==========================================================
# CRAWL4AI PRIMARY
# ==========================================================

@retry(
    stop=stop_after_attempt(2),
    wait=wait_random_exponential(
        multiplier=2,
        max=10,
    ),
)
async def crawl4ai_reviews(
    place_id,
    existing_ids=None,
    target_limit=50,
):

    logger.info("LEVEL 1 => CRAWL4AI")

    reviews = []

    seen = set()

    try:

        url = (
            "https://www.google.com/maps/search/"
            f"?api=1&query=Google&query_place_id={place_id}"
        )

        browser_config = {}

        if PROXY_SERVER:

            browser_config["proxy"] = {
                "server": f"http://{PROXY_SERVER}"
            }

            if PROXY_USERNAME and PROXY_PASSWORD:

                browser_config["proxy"]["username"] = PROXY_USERNAME

                browser_config["proxy"]["password"] = PROXY_PASSWORD

        async with AsyncWebCrawler(
            verbose=False,
            browser_config=browser_config,
        ) as crawler:

            result = await crawler.arun(
                url=url,
                bypass_cache=True,
                js_only=False,
                word_count_threshold=10,
                wait_until="networkidle",
                delay_before_return_html=8,
            )

            html = result.html

            if not html:

                logger.warning("EMPTY HTML")

                return []

            soup = BeautifulSoup(html, "lxml")

            blocks = soup.find_all("div")

            logger.info(f"TOTAL HTML BLOCKS => {len(blocks)}")

            for block in blocks:

                try:

                    text = clean_text(block.get_text())

                    if len(text) < 30:
                        continue

                    if "stars" not in text.lower():
                        continue

                    normalized = normalize_review(
                        {
                            "author": "Google User",
                            "text": text,
                            "rating": 5,
                            "date": "",
                        },
                        existing_ids,
                        seen,
                    )

                    if not normalized:
                        continue

                    reviews.append(normalized)

                    if len(reviews) >= target_limit:
                        break

                except Exception:
                    pass

        logger.info(f"CRAWL4AI REVIEWS => {len(reviews)}")

        return reviews

    except Exception as e:

        logger.exception(f"CRAWL4AI FAILED => {e}")

        return []

# ==========================================================
# PLAYWRIGHT SECONDARY
# ==========================================================

@retry(
    stop=stop_after_attempt(2),
    wait=wait_random_exponential(
        multiplier=2,
        max=10,
    ),
)
async def playwright_reviews(
    place_id,
    existing_ids=None,
    target_limit=50,
):

    logger.info("LEVEL 2 => PLAYWRIGHT")

    reviews = []

    existing_ids = existing_ids or set()

    browser = None
    context = None
    page = None

    try:

        async with async_playwright() as p:

            launch_options = {
                "headless": HEADLESS,
                "args": [
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-infobars",
                    "--disable-gpu",
                    "--disable-web-security",
                    "--window-size=1920,1080",
                ],
            }

            if PROXY_SERVER:

                launch_options["proxy"] = {
                    "server": f"http://{PROXY_SERVER}"
                }

                if PROXY_USERNAME and PROXY_PASSWORD:

                    launch_options["proxy"]["username"] = PROXY_USERNAME

                    launch_options["proxy"]["password"] = PROXY_PASSWORD

            browser = await p.chromium.launch(
                **launch_options
            )

            context = await browser.new_context(
                user_agent=get_user_agent(),
                viewport={
                    "width": 1920,
                    "height": 1080,
                },
                java_script_enabled=True,
                locale="en-US",
            )

            page = await context.new_page()

            await stealth_async(page)

            page.set_default_timeout(
                PLAYWRIGHT_TIMEOUT
            )

            page.set_default_navigation_timeout(
                PLAYWRIGHT_TIMEOUT
            )

            url = (
                "https://www.google.com/maps/search/"
                f"?api=1&query=Google&query_place_id={place_id}"
            )

            logger.info(f"OPENING => {url}")

            await page.goto(
                url,
                wait_until="domcontentloaded",
            )

            await page.wait_for_timeout(8000)

            selectors = [
                'button[jsaction*="pane.reviewChart.moreReviews"]',
                '[aria-label*="reviews"]',
                'button:has-text("Reviews")',
            ]

            for selector in selectors:

                try:

                    button = page.locator(selector).first

                    if await button.count() > 0:

                        await button.click()

                        logger.info(
                            f"CLICKED => {selector}"
                        )

                        break

                except Exception:
                    pass

            await page.wait_for_timeout(5000)

            feed = page.locator(
                'div[role="feed"]'
            ).first

            last_height = 0

            empty_scrolls = 0

            for _ in range(MAX_SCROLLS):

                try:

                    current_height = await feed.evaluate(
                        "(el) => el.scrollHeight"
                    )

                    await feed.evaluate(
                        "(el) => el.scrollTo(0, el.scrollHeight)"
                    )

                    await page.wait_for_timeout(
                        random.randint(
                            1500,
                            3000,
                        )
                    )

                    new_height = await feed.evaluate(
                        "(el) => el.scrollHeight"
                    )

                    if new_height == last_height:

                        empty_scrolls += 1

                    else:

                        empty_scrolls = 0

                    last_height = new_height

                    if empty_scrolls >= 8:
                        break

                except Exception:
                    pass

            cards = page.locator(
                "div.jftiEf"
            )

            count = await cards.count()

            logger.info(f"TOTAL CARDS => {count}")

            seen = set()

            for i in range(count):

                try:

                    card = cards.nth(i)

                    author = "Anonymous"

                    try:

                        author = clean_text(
                            await card.locator(
                                ".d4r55"
                            ).inner_text()
                        )

                    except Exception:
                        pass

                    text = ""

                    for selector in [
                        ".wiI7pd",
                        ".MyEned",
                        ".jJc9Ad",
                    ]:

                        try:

                            text = clean_text(
                                await card.locator(
                                    selector
                                ).inner_text()
                            )

                            if text:
                                break

                        except Exception:
                            pass

                    if not text:
                        continue

                    rating = 5

                    try:

                        rating_element = card.locator(
                            'span[aria-label*="star"]'
                        ).first

                        aria = await rating_element.get_attribute(
                            "aria-label"
                        )

                        match = re.search(
                            r"(\\d+)",
                            str(aria),
                        )

                        if match:
                            rating = int(match.group(1))

                    except Exception:
                        pass

                    review_date = ""

                    try:

                        review_date = clean_text(
                            await card.locator(
                                ".rsqaWe"
                            ).inner_text()
                        )

                    except Exception:
                        pass

                    normalized = normalize_review(
                        {
                            "author": author,
                            "text": text,
                            "rating": rating,
                            "date": review_date,
                        },
                        existing_ids,
                        seen,
                    )

                    if not normalized:
                        continue

                    reviews.append(normalized)

                    if len(reviews) >= target_limit:
                        break

                except Exception as e:

                    logger.warning(
                        f"CARD FAILED => {e}"
                    )

            logger.info(
                f"PLAYWRIGHT REVIEWS => {len(reviews)}"
            )

            return reviews

    except Exception as e:

        logger.exception(
            f"PLAYWRIGHT FAILED => {e}"
        )

        return []

    finally:

        try:
            if page:
                await page.close()
        except Exception:
            pass

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

        gc.collect()

# ==========================================================
# MASTER SCRAPER
# ==========================================================

async def scrape_google_reviews(
    place_id,
    existing_ids=None,
    target_limit=50,
):

    logger.info(
        f"START SCRAPING => {place_id}"
    )

    # ======================================================
    # LEVEL 1
    # ======================================================

    reviews = await crawl4ai_reviews(
        place_id,
        existing_ids,
        target_limit,
    )

    if reviews:

        logger.info(
            f"CRAWL4AI SUCCESS => {len(reviews)}"
        )

        return reviews

    # ======================================================
    # LEVEL 2
    # ======================================================

    reviews = await playwright_reviews(
        place_id,
        existing_ids,
        target_limit,
    )

    if reviews:

        logger.info(
            f"PLAYWRIGHT SUCCESS => {len(reviews)}"
        )

        return reviews

    # ======================================================
    # LEVEL 3
    # ======================================================

    reviews = await serpapi_reviews(
        place_id,
        existing_ids,
        target_limit,
    )

    if reviews:

        logger.info(
            f"SERPAPI SUCCESS => {len(reviews)}"
        )

        return reviews

    logger.warning("NO REVIEWS FOUND")

    return []

# ==========================================================
# BACKWARD COMPATIBILITY
# IMPORTANT
# ==========================================================

async def scrape_reviews(*args, **kwargs):

    return await scrape_google_reviews(
        *args,
        **kwargs,
    )

async def sync_google_reviews(*args, **kwargs):

    return await scrape_google_reviews(
        *args,
        **kwargs,
    )

# ==========================================================
# TEST
# ==========================================================

async def main():

    place_id = "ChIJN1t_tDeuEmsRUsoyG83frY4"

    reviews = await scrape_google_reviews(
        place_id=place_id,
        target_limit=10,
    )

    print(
        json.dumps(
            reviews,
            indent=2,
            ensure_ascii=False,
        )
    )

if __name__ == "__main__":

    asyncio.run(main())
