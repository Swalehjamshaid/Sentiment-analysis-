# =========================================================
# FILE: app/scraper.py
# TRUSTLYTICS AI - ULTRA ENTERPRISE SCRAPER
# 2026 WORLD CLASS EDITION
# =========================================================

import os
import re
import json
import asyncio
import logging
import traceback
import random

from datetime import datetime
from typing import List, Dict, Any

# =========================================================
# LOGGER
# =========================================================

logger = logging.getLogger(__name__)

logger.setLevel(logging.INFO)

# =========================================================
# PROXY CONFIG
# =========================================================

PROXY_USERNAME = "f24ab799ffcf42cf2c54"

PROXY_PASSWORD = "e25628cf2c1b3ba3"

PROXY_SERVER = "gw.dataimpulse.com:823"

# =========================================================
# PROXY URL
# =========================================================

PROXY_URL = (
    f"http://{PROXY_USERNAME}:"
    f"{PROXY_PASSWORD}@"
    f"{PROXY_SERVER}"
)

# =========================================================
# SERPAPI
# =========================================================

SERPAPI_KEY = os.getenv(
    "SERPAPI_KEY",
    ""
)

# =========================================================
# PLAYWRIGHT
# =========================================================

from playwright.async_api import (
    async_playwright,
    TimeoutError as PlaywrightTimeout
)

from playwright_stealth import stealth_async

# =========================================================
# PARSERS
# =========================================================

from bs4 import BeautifulSoup

from lxml import html

from selectolax.parser import HTMLParser

# =========================================================
# USER AGENT
# =========================================================

from fake_useragent import UserAgent

ua = UserAgent()

# =========================================================
# RETRY
# =========================================================

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential
)

import backoff

# =========================================================
# FILE SUPPORT
# =========================================================

import aiofiles

import aiosqlite

# =========================================================
# CURL_CFFI
# =========================================================

from curl_cffi.requests import Session

# =========================================================
# OPTIONAL CRAWL4AI
# =========================================================

CRAWL4AI_AVAILABLE = False

try:

    from crawl4ai import AsyncWebCrawler

    CRAWL4AI_AVAILABLE = True

    logger.info(
        "✅ CRAWL4AI AVAILABLE"
    )

except Exception as e:

    logger.warning(
        f"❌ CRAWL4AI NOT AVAILABLE => {e}"
    )

# =========================================================
# HUMAN DELAY
# =========================================================

async def human_delay(
    minimum: float = 1.0,
    maximum: float = 3.0
):

    await asyncio.sleep(
        random.uniform(minimum, maximum)
    )

# =========================================================
# SENTIMENT
# =========================================================

def simple_sentiment(
    text: str
):

    text = text.lower()

    positive_words = [

        "good",
        "great",
        "excellent",
        "perfect",
        "love",
        "amazing",
        "awesome",
        "best",
        "fantastic"
    ]

    negative_words = [

        "bad",
        "worst",
        "terrible",
        "awful",
        "hate",
        "poor",
        "dirty",
        "rude"
    ]

    positive_score = sum(
        1 for word in positive_words
        if word in text
    )

    negative_score = sum(
        1 for word in negative_words
        if word in text
    )

    if positive_score > negative_score:

        return "positive"

    if negative_score > positive_score:

        return "negative"

    return "neutral"

# =========================================================
# NORMALIZE REVIEW
# =========================================================

def normalize_review(
    review: Dict[str, Any]
):

    review_text = str(
        review.get(
            "review_text",
            ""
        )
    ).strip()

    if not review_text:

        return {}

    author = str(
        review.get(
            "author",
            "Anonymous"
        )
    ).strip()

    rating = int(
        review.get(
            "rating",
            5
        ) or 5
    )

    return {

        "author": author,

        "rating": rating,

        "review_text": review_text,

        "sentiment": simple_sentiment(
            review_text
        ),

        "source": review.get(
            "source",
            "Google"
        ),

        "review_date":
            datetime.utcnow()
    }

# =========================================================
# DEDUPLICATION
# =========================================================

def deduplicate_reviews(
    reviews: List[Dict]
):

    unique_reviews = []

    seen = set()

    for review in reviews:

        text = review.get(
            "review_text",
            ""
        ).strip()

        author = review.get(
            "author",
            ""
        ).strip()

        key = f"{author}_{text}"

        if key in seen:

            continue

        seen.add(key)

        unique_reviews.append(review)

    return unique_reviews

# =========================================================
# SERPAPI PRIMARY
# =========================================================

@backoff.on_exception(
    backoff.expo,
    Exception,
    max_tries=3
)

def serpapi_reviews(
    place_id: str
):

    logger.info(
        "🚀 SERPAPI STARTED"
    )

    reviews = []

    if not SERPAPI_KEY:

        logger.warning(
            "❌ SERPAPI KEY MISSING"
        )

        return reviews

    try:

        import requests

        response = requests.get(

            "https://serpapi.com/search.json",

            params={

                "engine":
                    "google_maps_reviews",

                "place_id":
                    place_id,

                "api_key":
                    SERPAPI_KEY,

                "hl":
                    "en"
            },

            timeout=120
        )

        data = response.json()

        raw_reviews = data.get(
            "reviews",
            []
        )

        for item in raw_reviews:

            review = normalize_review({

                "author":
                    item.get(
                        "user",
                        "SERPAPI User"
                    ),

                "rating":
                    item.get(
                        "rating",
                        5
                    ),

                "review_text":
                    item.get(
                        "snippet",
                        ""
                    ),

                "source":
                    "SERPAPI"
            })

            if review:

                reviews.append(review)

        logger.info(
            f"✅ SERPAPI REVIEWS => {len(reviews)}"
        )

    except Exception as e:

        logger.error(
            f"❌ SERPAPI ERROR => {e}"
        )

    return reviews

# =========================================================
# PLAYWRIGHT SCRAPER
# =========================================================

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2)
)

async def playwright_reviews(
    place_id: str
):

    logger.info(
        "🚀 PLAYWRIGHT STARTED"
    )

    reviews = []

    async with async_playwright() as p:

        browser = await p.chromium.launch(

            headless=True,

            proxy={

                "server":
                    f"http://{PROXY_SERVER}",

                "username":
                    PROXY_USERNAME,

                "password":
                    PROXY_PASSWORD
            },

            args=[

                "--disable-blink-features=AutomationControlled",

                "--disable-dev-shm-usage",

                "--no-sandbox",

                "--disable-setuid-sandbox",

                "--disable-infobars",

                "--window-size=1920,1080"
            ]
        )

        context = await browser.new_context(

            user_agent=ua.random,

            viewport={

                "width": 1920,

                "height": 1080
            },

            locale="en-US"
        )

        page = await context.new_page()

        await stealth_async(page)

        url = (
            "https://www.google.com/maps/place/"
            f"?q=place_id:{place_id}"
        )

        logger.info(
            f"🌍 OPENING => {url}"
        )

        await page.goto(

            url,

            timeout=120000,

            wait_until="networkidle"
        )

        await human_delay(3, 5)

        try:

            reviews_button = page.locator(

                'button[jsaction*="pane.reviewChart.moreReviews"]'
            )

            await reviews_button.click()

            logger.info(
                "✅ REVIEW BUTTON CLICKED"
            )

        except Exception:

            logger.warning(
                "❌ REVIEW BUTTON NOT FOUND"
            )

        await human_delay(3, 5)

        # =================================================
        # DEEP SCROLL
        # =================================================

        for _ in range(50):

            await page.mouse.wheel(
                0,
                10000
            )

            await human_delay(1, 2)

        html_content = await page.content()

        soup = BeautifulSoup(
            html_content,
            "lxml"
        )

        review_blocks = soup.select(
            "div.jftiEf"
        )

        logger.info(
            f"✅ PLAYWRIGHT BLOCKS => {len(review_blocks)}"
        )

        for block in review_blocks:

            try:

                author = ""

                rating = 5

                review_text = ""

                author_element = block.select_one(
                    ".d4r55"
                )

                if author_element:

                    author = author_element.text.strip()

                review_element = block.select_one(
                    ".wiI7pd"
                )

                if review_element:

                    review_text = review_element.text.strip()

                rating_element = block.select_one(
                    "span.kvMYJc"
                )

                if rating_element:

                    aria = rating_element.get(
                        "aria-label",
                        ""
                    )

                    match = re.search(
                        r"(\d)",
                        aria
                    )

                    if match:

                        rating = int(
                            match.group(1)
                        )

                if review_text:

                    review = normalize_review({

                        "author": author,

                        "rating": rating,

                        "review_text": review_text,

                        "source": "PLAYWRIGHT"
                    })

                    if review:

                        reviews.append(review)

            except Exception as parse_error:

                logger.error(
                    f"❌ PLAYWRIGHT PARSE ERROR => {parse_error}"
                )

        await browser.close()

    logger.info(
        f"✅ PLAYWRIGHT SCRAPED => {len(reviews)}"
    )

    return reviews

# =========================================================
# CURL_CFFI FALLBACK
# =========================================================

def curl_reviews(
    place_id: str
):

    logger.info(
        "🚀 CURL_CFFI STARTED"
    )

    reviews = []

    try:

        session = Session()

        response = session.get(

            (
                "https://www.google.com/maps/place/"
                f"?q=place_id:{place_id}"
            ),

            impersonate="chrome124",

            proxies={

                "http": PROXY_URL,

                "https": PROXY_URL
            },

            headers={

                "User-Agent":
                    ua.random
            },

            timeout=120
        )

        parser = HTMLParser(
            response.text
        )

        nodes = parser.css(
            ".wiI7pd"
        )

        logger.info(
            f"✅ CURL NODES => {len(nodes)}"
        )

        for node in nodes:

            review_text = node.text().strip()

            if review_text:

                review = normalize_review({

                    "author":
                        "Curl User",

                    "rating":
                        5,

                    "review_text":
                        review_text,

                    "source":
                        "CURL_CFFI"
                })

                if review:

                    reviews.append(review)

    except Exception as e:

        logger.error(
            f"❌ CURL ERROR => {e}"
        )

    logger.info(
        f"✅ CURL SCRAPED => {len(reviews)}"
    )

    return reviews

# =========================================================
# CRAWL4AI
# =========================================================

async def crawl4ai_reviews(
    place_id: str
):

    reviews = []

    if not CRAWL4AI_AVAILABLE:

        return reviews

    try:

        logger.info(
            "🚀 CRAWL4AI STARTED"
        )

        async with AsyncWebCrawler() as crawler:

            result = await crawler.arun(

                url=(
                    "https://www.google.com/maps/place/"
                    f"?q=place_id:{place_id}"
                )
            )

            html_content = result.html

            soup = BeautifulSoup(
                html_content,
                "lxml"
            )

            elements = soup.select(
                ".wiI7pd"
            )

            logger.info(
                f"✅ CRAWL4AI ELEMENTS => {len(elements)}"
            )

            for item in elements:

                review_text = item.text.strip()

                if review_text:

                    review = normalize_review({

                        "author":
                            "Crawler User",

                        "rating":
                            5,

                        "review_text":
                            review_text,

                        "source":
                            "CRAWL4AI"
                    })

                    if review:

                        reviews.append(review)

    except Exception as e:

        logger.error(
            f"❌ CRAWL4AI ERROR => {e}"
        )

    logger.info(
        f"✅ CRAWL4AI SCRAPED => {len(reviews)}"
    )

    return reviews

# =========================================================
# MASTER SCRAPER
# =========================================================

async def scrape_google_reviews(
    place_id: str
):

    logger.info(
        f"🚀 MASTER SCRAPER STARTED => {place_id}"
    )

    all_reviews = []

    try:

        # =================================================
        # SERPAPI FIRST
        # =================================================

        serp_reviews = serpapi_reviews(
            place_id
        )

        all_reviews.extend(
            serp_reviews
        )

        logger.info(
            f"📊 AFTER SERPAPI => {len(all_reviews)}"
        )

        # =================================================
        # PLAYWRIGHT
        # =================================================

        if len(all_reviews) < 100:

            playwright_result = await playwright_reviews(
                place_id
            )

            all_reviews.extend(
                playwright_result
            )

            logger.info(
                f"📊 AFTER PLAYWRIGHT => {len(all_reviews)}"
            )

        # =================================================
        # CURL_CFFI
        # =================================================

        if len(all_reviews) < 100:

            curl_result = curl_reviews(
                place_id
            )

            all_reviews.extend(
                curl_result
            )

            logger.info(
                f"📊 AFTER CURL => {len(all_reviews)}"
            )

        # =================================================
        # CRAWL4AI
        # =================================================

        if len(all_reviews) < 100:

            crawl_result = await crawl4ai_reviews(
                place_id
            )

            all_reviews.extend(
                crawl_result
            )

            logger.info(
                f"📊 AFTER CRAWL4AI => {len(all_reviews)}"
            )

        # =================================================
        # DEDUPLICATION
        # =================================================

        all_reviews = deduplicate_reviews(
            all_reviews
        )

        logger.info(
            f"✅ FINAL UNIQUE REVIEWS => {len(all_reviews)}"
        )

        return all_reviews

    except Exception as e:

        logger.error(
            f"❌ MASTER SCRAPER ERROR => {e}"
        )

        logger.error(
            traceback.format_exc()
        )

        return []

# =========================================================
# TEST
# =========================================================

if __name__ == "__main__":

    async def main():

        place_id = "ChIJN1t_tDeuEmsRUsoyG83frY4"

        reviews = await scrape_google_reviews(
            place_id
        )

        print(
            json.dumps(
                reviews[:5],
                indent=4,
                default=str
            )
        )

    asyncio.run(main())

# =========================================================
# END OF FILE
# =========================================================
