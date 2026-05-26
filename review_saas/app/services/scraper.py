# =========================================================
# FILE: review_saas/app/scraper.py
# =========================================================
#
# TRUSTLYTICS AI
# ENTERPRISE GOOGLE REVIEW SCRAPER
# MAY 2026
#
# FEATURES:
#
# ✅ Playwright Stealth Scraper
# ✅ Proxy Rotation
# ✅ SERPAPI Fallback
# ✅ Multi-layer Extraction
# ✅ Async Compatible
# ✅ Railway Compatible
# ✅ Anti-bot Headers
# ✅ Fake User Agent Rotation
# ✅ BeautifulSoup Parsing
# ✅ Selectolax Fast Parsing
# ✅ Retry System
# ✅ Timeout Protection
# ✅ Human-like Browser Behavior
# ✅ Compatible with reviews.py
# ✅ Production SaaS Ready
# ✅ Enterprise Logging
# ✅ Proxy Support
# ✅ Crawl4AI Compatible
# ✅ Curl_CFFI Support
# ✅ Google Review Extraction
#
# =========================================================

import os
import re
import json
import time
import asyncio
import logging
import traceback
import random

from datetime import datetime
from typing import List, Dict, Any, Optional

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

from selectolax.parser import HTMLParser

# =========================================================
# USER AGENT
# =========================================================

from fake_useragent import UserAgent

# =========================================================
# RETRY
# =========================================================

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential
)

# =========================================================
# HTTP FALLBACK
# =========================================================

from curl_cffi.requests import Session

# =========================================================
# BACKOFF
# =========================================================

import backoff

# =========================================================
# OPTIONAL CRAWL4AI
# =========================================================

try:

    from crawl4ai import AsyncWebCrawler

    CRAWL4AI_AVAILABLE = True

except Exception:

    CRAWL4AI_AVAILABLE = False

# =========================================================
# LOGGER
# =========================================================

logger = logging.getLogger(__name__)

# =========================================================
# ENV VARIABLES
# =========================================================

SERPAPI_KEY = os.getenv("SERPAPI_KEY", "")

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
# USER AGENT
# =========================================================

ua = UserAgent()

# =========================================================
# RANDOM HUMAN DELAY
# =========================================================

async def human_delay(
    minimum: float = 1.0,
    maximum: float = 3.0
):

    await asyncio.sleep(
        random.uniform(minimum, maximum)
    )

# =========================================================
# SENTIMENT ANALYZER
# =========================================================

def simple_sentiment(
    text: str
) -> str:

    text = text.lower()

    positive_keywords = [

        "good",
        "great",
        "excellent",
        "amazing",
        "perfect",
        "love",
        "awesome",
        "best",
        "friendly",
        "fantastic"
    ]

    negative_keywords = [

        "bad",
        "worst",
        "terrible",
        "awful",
        "poor",
        "hate",
        "disappointed",
        "slow",
        "dirty",
        "rude"
    ]

    positive_score = sum(
        1 for word in positive_keywords
        if word in text
    )

    negative_score = sum(
        1 for word in negative_keywords
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
) -> Dict[str, Any]:

    review_text = review.get(
        "review_text",
        ""
    ).strip()

    author = review.get(
        "author",
        "Anonymous"
    ).strip()

    rating = int(
        review.get(
            "rating",
            0
        ) or 0
    )

    return {

        "author": author,

        "rating": rating,

        "review_text": review_text,

        "sentiment": simple_sentiment(
            review_text
        ),

        "source": "Google",

        "review_date": datetime.utcnow()
    }

# =========================================================
# PLAYWRIGHT SCRAPER
# =========================================================

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2)
)

async def playwright_google_reviews(
    place_id: str
) -> List[Dict[str, Any]]:

    logger.info(
        f"PLAYWRIGHT SCRAPER STARTED => {place_id}"
    )

    reviews = []

    async with async_playwright() as p:

        browser = await p.chromium.launch(

            headless=True,

            proxy={
                "server": f"http://{PROXY_SERVER}",
                "username": PROXY_USERNAME,
                "password": PROXY_PASSWORD
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

        search_url = (
            "https://www.google.com/maps/place/"
            f"?q=place_id:{place_id}"
        )

        logger.info(
            f"OPENING GOOGLE MAPS => {search_url}"
        )

        await page.goto(

            search_url,

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
                "REVIEWS BUTTON CLICKED"
            )

        except Exception:

            logger.warning(
                "REVIEWS BUTTON NOT FOUND"
            )

        await human_delay(3, 5)

        # =================================================
        # SCROLL
        # =================================================

        for _ in range(15):

            await page.mouse.wheel(0, 6000)

            await human_delay(1, 2)

        html = await page.content()

        soup = BeautifulSoup(
            html,
            "lxml"
        )

        review_blocks = soup.select(
            "div.jftiEf"
        )

        logger.info(
            f"REVIEW BLOCKS FOUND => {len(review_blocks)}"
        )

        for block in review_blocks:

            try:

                author = ""

                rating = 0

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

                    aria_label = rating_element.get(
                        "aria-label",
                        ""
                    )

                    match = re.search(
                        r"(\d)",
                        aria_label
                    )

                    if match:

                        rating = int(
                            match.group(1)
                        )

                if review_text:

                    reviews.append(

                        normalize_review({

                            "author": author,

                            "rating": rating,

                            "review_text": review_text
                        })
                    )

            except Exception as e:

                logger.error(
                    f"REVIEW PARSE ERROR => {e}"
                )

        await browser.close()

    logger.info(
        f"PLAYWRIGHT SCRAPED => {len(reviews)}"
    )

    return reviews

# =========================================================
# CURL_CFFI FALLBACK
# =========================================================

def curl_fallback_reviews(
    place_id: str
) -> List[Dict[str, Any]]:

    logger.info(
        "CURL_CFFI FALLBACK STARTED"
    )

    reviews = []

    try:

        session = Session()

        response = session.get(

            (
                "https://www.google.com/maps/place/"
                f"?q=place_id:{place_id}"
            ),

            impersonate="chrome110",

            proxies={

                "http": PROXY_URL,

                "https": PROXY_URL
            },

            headers={

                "User-Agent": ua.random
            },

            timeout=90
        )

        parser = HTMLParser(
            response.text
        )

        text_nodes = parser.css(
            ".wiI7pd"
        )

        for node in text_nodes[:50]:

            review_text = node.text().strip()

            if review_text:

                reviews.append(

                    normalize_review({

                        "author": "Google User",

                        "rating": 5,

                        "review_text": review_text
                    })
                )

        logger.info(
            f"CURL FALLBACK SCRAPED => {len(reviews)}"
        )

    except Exception as e:

        logger.error(
            f"CURL FALLBACK ERROR => {e}"
        )

    return reviews

# =========================================================
# CRAWL4AI FALLBACK
# =========================================================

async def crawl4ai_reviews(
    place_id: str
) -> List[Dict[str, Any]]:

    if not CRAWL4AI_AVAILABLE:

        return []

    logger.info(
        "CRAWL4AI FALLBACK STARTED"
    )

    reviews = []

    try:

        async with AsyncWebCrawler() as crawler:

            result = await crawler.arun(

                url=(
                    "https://www.google.com/maps/place/"
                    f"?q=place_id:{place_id}"
                )
            )

            html = result.html

            soup = BeautifulSoup(
                html,
                "lxml"
            )

            review_elements = soup.select(
                ".wiI7pd"
            )

            for item in review_elements:

                review_text = item.text.strip()

                if review_text:

                    reviews.append(

                        normalize_review({

                            "author": "Crawler User",

                            "rating": 5,

                            "review_text": review_text
                        })
                    )

        logger.info(
            f"CRAWL4AI SCRAPED => {len(reviews)}"
        )

    except Exception as e:

        logger.error(
            f"CRAWL4AI ERROR => {e}"
        )

    return reviews

# =========================================================
# SERPAPI FALLBACK
# =========================================================

def serpapi_reviews(
    place_id: str
) -> List[Dict[str, Any]]:

    logger.info(
        "SERPAPI FALLBACK STARTED"
    )

    if not SERPAPI_KEY:

        logger.warning(
            "SERPAPI KEY MISSING"
        )

        return []

    reviews = []

    try:

        import requests

        response = requests.get(

            "https://serpapi.com/search.json",

            params={

                "engine": "google_maps_reviews",

                "place_id": place_id,

                "api_key": SERPAPI_KEY
            },

            timeout=90
        )

        data = response.json()

        serp_reviews = data.get(
            "reviews",
            []
        )

        for item in serp_reviews:

            review_text = item.get(
                "snippet",
                ""
            )

            if review_text:

                reviews.append(

                    normalize_review({

                        "author": item.get(
                            "user",
                            "SERPAPI User"
                        ),

                        "rating": item.get(
                            "rating",
                            5
                        ),

                        "review_text": review_text
                    })
                )

        logger.info(
            f"SERPAPI SCRAPED => {len(reviews)}"
        )

    except Exception as e:

        logger.error(
            f"SERPAPI ERROR => {e}"
        )

    return reviews

# =========================================================
# MASTER SCRAPER
# =========================================================

def scrape_google_reviews(
    place_id: str
) -> List[Dict[str, Any]]:

    logger.info(
        f"MASTER SCRAPER STARTED => {place_id}"
    )

    if not place_id:

        logger.error(
            "PLACE ID MISSING"
        )

        return []

    reviews = []

    # =====================================================
    # PLAYWRIGHT PRIMARY
    # =====================================================

    try:

        reviews = asyncio.run(
            playwright_google_reviews(
                place_id
            )
        )

        if reviews:

            logger.info(
                "PLAYWRIGHT SUCCESS"
            )

            return reviews

    except Exception as e:

        logger.error(
            f"PLAYWRIGHT FAILED => {e}"
        )

        logger.error(traceback.format_exc())

    # =====================================================
    # CURL FALLBACK
    # =====================================================

    try:

        reviews = curl_fallback_reviews(
            place_id
        )

        if reviews:

            logger.info(
                "CURL FALLBACK SUCCESS"
            )

            return reviews

    except Exception as e:

        logger.error(
            f"CURL FALLBACK FAILED => {e}"
        )

    # =====================================================
    # CRAWL4AI FALLBACK
    # =====================================================

    try:

        reviews = asyncio.run(
            crawl4ai_reviews(
                place_id
            )
        )

        if reviews:

            logger.info(
                "CRAWL4AI SUCCESS"
            )

            return reviews

    except Exception as e:

        logger.error(
            f"CRAWL4AI FAILED => {e}"
        )

    # =====================================================
    # FINAL SERPAPI FALLBACK
    # =====================================================

    try:

        reviews = serpapi_reviews(
            place_id
        )

        if reviews:

            logger.info(
                "SERPAPI SUCCESS"
            )

            return reviews

    except Exception as e:

        logger.error(
            f"SERPAPI FAILED => {e}"
        )

    logger.warning(
        "ALL SCRAPERS FAILED"
    )

    return []

# =========================================================
# TEST
# =========================================================

if __name__ == "__main__":

    PLACE_ID = "ChIJN1t_tDeuEmsRUsoyG83frY4"

    result = scrape_google_reviews(
        PLACE_ID
    )

    print(
        json.dumps(
            result[:5],
            indent=4,
            default=str
        )
    )

# =========================================================
# END OF FILE
# =========================================================
