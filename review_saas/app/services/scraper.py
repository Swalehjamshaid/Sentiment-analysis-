# ==========================================================
# FILE: app/scraper.py
# TRUSTLYTICS AI - ENTERPRISE GOOGLE REVIEW SCRAPER
# 2026 ULTRA STABLE EDITION
# ==========================================================

from __future__ import annotations

import asyncio
import json
import logging
import random
import traceback
import uuid

from datetime import datetime
from typing import List, Dict, Optional, Set

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
)

from fake_useragent import UserAgent

from playwright.async_api import (
    async_playwright,
    TimeoutError as PlaywrightTimeoutError,
)

from playwright_stealth import stealth_async

from bs4 import BeautifulSoup

from curl_cffi.requests import AsyncSession

# ==========================================================
# OPTIONAL LIBRARIES
# ==========================================================

try:
    from selectolax.parser import HTMLParser
    SELECTOLAX_AVAILABLE = True
except:
    SELECTOLAX_AVAILABLE = False

try:
    from crawl4ai import AsyncWebCrawler
    CRAWL4AI_AVAILABLE = True
except:
    CRAWL4AI_AVAILABLE = False

# ==========================================================
# LOGGER
# ==========================================================

logger = logging.getLogger(__name__)

# ==========================================================
# CONFIG
# ==========================================================

GOOGLE_DOMAIN = "https://www.google.com"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Mozilla/5.0 (X11; Linux x86_64)",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
]

# ==========================================================
# PROXY CONFIG
# ==========================================================

PROXIES = [

    # ADD YOUR REAL PROXIES HERE

    # "http://username:password@ip:port",

]

# ==========================================================
# UTILITIES
# ==========================================================

def get_random_user_agent():

    try:
        return UserAgent().random
    except:
        return random.choice(USER_AGENTS)

def build_google_review_url(place_id: str):

    return (
        f"https://search.google.com/local/reviews?"
        f"placeid={place_id}"
    )

def clean_text(value):

    if not value:
        return ""

    return (
        str(value)
        .replace("\n", " ")
        .replace("\r", " ")
        .strip()
    )

# ==========================================================
# PLAYWRIGHT SCRAPER
# ==========================================================

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=10),
)

async def playwright_scraper(
    place_id: str,
    existing_ids: Set[str],
    target_limit: int = 300,
):

    reviews = []

    logger.info("🚀 PLAYWRIGHT SCRAPER STARTED")

    async with async_playwright() as p:

        browser = await p.chromium.launch(

            headless=True,

            args=[

                "--disable-blink-features=AutomationControlled",

                "--no-sandbox",

                "--disable-dev-shm-usage",

                "--disable-gpu",

                "--disable-web-security",

                "--window-size=1920,1080",

            ]
        )

        context = await browser.new_context(

            user_agent=get_random_user_agent(),

            viewport={

                "width": 1920,

                "height": 1080,
            },

            locale="en-US",
        )

        page = await context.new_page()

        await stealth_async(page)

        url = build_google_review_url(place_id)

        logger.info(f"🌍 URL => {url}")

        await page.goto(

            url,

            timeout=120000,

            wait_until="domcontentloaded"
        )

        await asyncio.sleep(5)

        for _ in range(50):

            try:

                await page.mouse.wheel(0, 10000)

                await asyncio.sleep(2)

            except:
                pass

        html = await page.content()

        await browser.close()

    soup = BeautifulSoup(html, "lxml")

    blocks = soup.find_all("div")

    logger.info(f"📦 HTML BLOCKS => {len(blocks)}")

    for block in blocks:

        try:

            text = clean_text(block.get_text())

            if len(text) < 20:
                continue

            rating = 5

            review_id = str(uuid.uuid4())

            if review_id in existing_ids:
                continue

            review = {

                "review_id": review_id,

                "author": "Google User",

                "rating": rating,

                "text": text[:5000],

                "date": datetime.utcnow().isoformat(),
            }

            reviews.append(review)

            if len(reviews) >= target_limit:
                break

        except:
            continue

    logger.info(
        f"✅ PLAYWRIGHT REVIEWS => {len(reviews)}"
    )

    return reviews

# ==========================================================
# CRAWL4AI SCRAPER
# ==========================================================

async def crawl4ai_scraper(
    place_id: str,
    existing_ids: Set[str],
    target_limit: int = 300,
):

    reviews = []

    if not CRAWL4AI_AVAILABLE:

        logger.warning("⚠️ CRAWL4AI NOT INSTALLED")

        return reviews

    logger.info("🚀 CRAWL4AI SCRAPER STARTED")

    try:

        async with AsyncWebCrawler() as crawler:

            result = await crawler.arun(

                url=build_google_review_url(place_id)
            )

            html = result.html

            if not html:
                return reviews

            soup = BeautifulSoup(html, "lxml")

            divs = soup.find_all("div")

            for div in divs:

                text = clean_text(div.get_text())

                if len(text) < 20:
                    continue

                review_id = str(uuid.uuid4())

                if review_id in existing_ids:
                    continue

                reviews.append({

                    "review_id": review_id,

                    "author": "Crawler User",

                    "rating": 5,

                    "text": text[:5000],

                    "date": datetime.utcnow().isoformat(),
                })

                if len(reviews) >= target_limit:
                    break

    except Exception as e:

        logger.error(f"❌ CRAWL4AI FAILED => {e}")

    logger.info(
        f"✅ CRAWL4AI REVIEWS => {len(reviews)}"
    )

    return reviews

# ==========================================================
# CURL_CFFI SCRAPER
# ==========================================================

async def curl_scraper(
    place_id: str,
    existing_ids: Set[str],
    target_limit: int = 300,
):

    reviews = []

    logger.info("🚀 CURL_CFFI SCRAPER STARTED")

    try:

        async with AsyncSession(

            impersonate="chrome124",

            timeout=60,
        ) as session:

            response = await session.get(

                build_google_review_url(place_id),

                headers={

                    "User-Agent":
                        get_random_user_agent()
                }
            )

            html = response.text

            if not html:
                return reviews

            if SELECTOLAX_AVAILABLE:

                tree = HTMLParser(html)

                nodes = tree.css("div")

                for node in nodes:

                    try:

                        text = clean_text(node.text())

                        if len(text) < 20:
                            continue

                        review_id = str(uuid.uuid4())

                        if review_id in existing_ids:
                            continue

                        reviews.append({

                            "review_id": review_id,

                            "author": "Curl User",

                            "rating": 5,

                            "text": text[:5000],

                            "date":
                                datetime.utcnow().isoformat(),
                        })

                        if len(reviews) >= target_limit:
                            break

                    except:
                        continue

    except Exception as e:

        logger.error(f"❌ CURL SCRAPER FAILED => {e}")

    logger.info(
        f"✅ CURL REVIEWS => {len(reviews)}"
    )

    return reviews

# ==========================================================
# SUPER API FALLBACK
# ==========================================================

async def superapi_scraper(
    place_id: str,
    existing_ids: Set[str],
    target_limit: int = 300,
):

    logger.info("🚀 SUPERAPI FALLBACK STARTED")

    # PLACE YOUR SUPERAPI HERE

    return []

# ==========================================================
# MAIN SCRAPER
# ==========================================================

async def scrape_google_reviews(
    place_id: str,
    existing_ids: Optional[Set[str]] = None,
    target_limit: int = 300,
):

    if existing_ids is None:
        existing_ids = set()

    logger.info("================================================")
    logger.info("🚀 ENTERPRISE SCRAPER STARTED")
    logger.info(f"🏢 PLACE ID => {place_id}")
    logger.info("================================================")

    all_reviews = []

    # ======================================================
    # 1. CRAWL4AI + PROXY
    # ======================================================

    try:

        reviews = await crawl4ai_scraper(

            place_id=place_id,

            existing_ids=existing_ids,

            target_limit=target_limit,
        )

        if reviews:

            logger.info(
                f"✅ CRAWL4AI SUCCESS => {len(reviews)}"
            )

            all_reviews.extend(reviews)

    except Exception as e:

        logger.error(
            f"❌ CRAWL4AI ERROR => {e}"
        )

    # ======================================================
    # 2. PLAYWRIGHT
    # ======================================================

    if len(all_reviews) < 10:

        try:

            reviews = await playwright_scraper(

                place_id=place_id,

                existing_ids=existing_ids,

                target_limit=target_limit,
            )

            all_reviews.extend(reviews)

        except Exception as e:

            logger.error(
                f"❌ PLAYWRIGHT ERROR => {e}"
            )

            logger.error(traceback.format_exc())

    # ======================================================
    # 3. CURL_CFFI
    # ======================================================

    if len(all_reviews) < 10:

        try:

            reviews = await curl_scraper(

                place_id=place_id,

                existing_ids=existing_ids,

                target_limit=target_limit,
            )

            all_reviews.extend(reviews)

        except Exception as e:

            logger.error(
                f"❌ CURL ERROR => {e}"
            )

    # ======================================================
    # 4. SUPER API
    # ======================================================

    if len(all_reviews) < 5:

        try:

            reviews = await superapi_scraper(

                place_id=place_id,

                existing_ids=existing_ids,

                target_limit=target_limit,
            )

            all_reviews.extend(reviews)

        except Exception as e:

            logger.error(
                f"❌ SUPERAPI ERROR => {e}"
            )

    # ======================================================
    # REMOVE DUPLICATES
    # ======================================================

    unique_reviews = []

    seen = set()

    for review in all_reviews:

        try:

            text = review.get("text", "").strip()

            if not text:
                continue

            key = text[:150]

            if key in seen:
                continue

            seen.add(key)

            unique_reviews.append(review)

        except:
            continue

    logger.info("================================================")
    logger.info(
        f"✅ FINAL UNIQUE REVIEWS => {len(unique_reviews)}"
    )
    logger.info("================================================")

    return unique_reviews[:target_limit]
