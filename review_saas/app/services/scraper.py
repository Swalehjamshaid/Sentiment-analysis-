# ==========================================================
# FILE: app/services/scraper.py
# ENTERPRISE HYBRID GOOGLE REVIEWS SCRAPER
# CRAWL4AI + PLAYWRIGHT + SERPAPI FALLBACK
# RAILWAY SAFE - MAY 2026
# ==========================================================

import os
import re
import gc
import json
import random
import asyncio
import hashlib
import logging

from datetime import datetime, timedelta

import httpx

from fake_useragent import UserAgent

from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

from tenacity import (
    retry,
    stop_after_attempt,
    wait_random_exponential,
)

from sqlalchemy import select
from sqlalchemy.inspection import inspect as sa_inspect

from bs4 import BeautifulSoup
from selectolax.parser import HTMLParser

from crawl4ai import AsyncWebCrawler

from app.core.db import AsyncSessionLocal
from app.core.models import Review

logger = logging.getLogger("app.services.scraper")

# ==========================================================
# ENV
# ==========================================================

SERPAPI_KEY = os.getenv("SERPAPI_KEY")

PROXY_SERVER = os.getenv("PROXY_SERVER")
PROXY_USERNAME = os.getenv("PROXY_USERNAME")
PROXY_PASSWORD = os.getenv("PROXY_PASSWORD")

ENABLE_PLAYWRIGHT_FALLBACK = (
    os.getenv("ENABLE_PLAYWRIGHT_FALLBACK", "true").lower() == "true"
)

ENABLE_CRAWL4AI = (
    os.getenv("ENABLE_CRAWL4AI", "true").lower() == "true"
)

# ==========================================================
# CONFIG
# ==========================================================

REQUEST_TIMEOUT = 120
PLAYWRIGHT_TIMEOUT = 70000

HEADLESS = True
MAX_SCROLLS = 25

# ==========================================================
# USER AGENTS
# ==========================================================

def get_user_agent():
    try:
        return UserAgent().random

    except Exception:
        return (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/126.0 Safari/537.36"
        )

# ==========================================================
# HELPERS
# ==========================================================

def clean_text(text):
    try:
        if not text:
            return ""

        text = str(text)

        text = text.replace("\n", " ")
        text = text.replace("\r", " ")
        text = text.replace("\t", " ")

        return " ".join(text.split())[:5000]

    except Exception:
        return ""


def safe_int(value, default=0):
    try:
        if value is None:
            return default

        if isinstance(value, str):
            match = re.search(r"\d+", value)

            if match:
                return int(match.group(0))

        return int(value)

    except Exception:
        return default


def generate_hash(*parts):
    raw = "_".join(
        [
            clean_text(part)
            for part in parts
            if part is not None
        ]
    )

    return hashlib.md5(
        raw.encode("utf-8")
    ).hexdigest()


def parse_relative_date(relative_text):
    try:
        if not relative_text:
            return datetime.utcnow()

        text = str(relative_text).lower().strip()

        now = datetime.utcnow()

        if "today" in text or "just now" in text:
            return now

        if "yesterday" in text:
            return now - timedelta(days=1)

        match = re.search(r"(\d+)", text)

        number = int(match.group(1)) if match else 1

        if "minute" in text:
            return now - timedelta(minutes=number)

        if "hour" in text:
            return now - timedelta(hours=number)

        if "day" in text:
            return now - timedelta(days=number)

        if "week" in text:
            return now - timedelta(weeks=number)

        if "month" in text:
            return now - timedelta(days=number * 30)

        if "year" in text:
            return now - timedelta(days=number * 365)

        return now

    except Exception:
        return datetime.utcnow()


def build_proxy_url():
    try:
        if not PROXY_SERVER:
            return None

        if PROXY_USERNAME and PROXY_PASSWORD:
            return (
                f"http://{PROXY_USERNAME}:"
                f"{PROXY_PASSWORD}@{PROXY_SERVER}"
            )

        return f"http://{PROXY_SERVER}"

    except Exception:
        return None


def get_random_proxy():
    return build_proxy_url()

# ==========================================================
# SQLALCHEMY HELPERS
# ==========================================================

def get_review_model_columns():
    try:
        return {
            column.key
            for column in sa_inspect(
                Review
            ).mapper.column_attrs
        }

    except Exception as e:
        logger.exception(
            f"MODEL INSPECTION FAILED => {e}"
        )

        return set()


def get_first_existing_column(columns):
    existing = get_review_model_columns()

    for column in columns:
        if column in existing:
            return column

    return None


async def load_existing_review_ids(company_id):
    existing = set()

    try:
        id_column_name = get_first_existing_column(
            [
                "google_review_id",
                "review_id",
                "external_review_id",
                "external_id",
                "hash",
            ]
        )

        if not id_column_name:
            return existing

        company_column_name = get_first_existing_column(
            [
                "company_id",
                "business_id",
            ]
        )

        id_column = getattr(Review, id_column_name)

        async with AsyncSessionLocal() as db:
            stmt = select(id_column)

            if company_id and company_column_name:
                stmt = stmt.where(
                    getattr(
                        Review,
                        company_column_name,
                    ) == company_id
                )

            result = await db.execute(stmt)

            rows = result.fetchall()

            for row in rows:
                if row[0]:
                    existing.add(str(row[0]))

        return existing

    except Exception as e:
        logger.exception(
            f"LOAD EXISTING IDS FAILED => {e}"
        )

        return set()

# ==========================================================
# NORMALIZATION
# ==========================================================

def normalize_review(
    review,
    existing_ids,
    seen,
    start_date=None,
    end_date=None,
):
    try:
        author = clean_text(
            review.get("author")
            or review.get("author_name")
            or review.get("reviewer_name")
            or "Anonymous"
        )

        text = clean_text(
            review.get("text")
            or review.get("review")
            or review.get("snippet")
            or ""
        )

        if not text:
            return None

        rating = safe_int(
            review.get("rating"),
            5,
        )

        review_date_text = clean_text(
            review.get("date")
            or review.get("review_date")
            or ""
        )

        review_datetime = parse_relative_date(
            review_date_text
        )

        if start_date and review_datetime < start_date:
            return None

        if end_date and review_datetime > end_date:
            return None

        google_review_id = clean_text(
            review.get("review_id")
            or review.get("id")
            or ""
        )

        if not google_review_id:
            google_review_id = generate_hash(
                author,
                text,
                str(rating),
                review_date_text,
            )

        if (
            google_review_id in seen
            or google_review_id in existing_ids
        ):
            return None

        seen.add(google_review_id)
        existing_ids.add(google_review_id)

        sentiment = (
            "positive"
            if rating >= 4
            else "negative"
        )

        return {
            "google_review_id": google_review_id,
            "author_name": author,
            "rating": rating,
            "review_date": review_date_text,
            "google_review_time": review_datetime,
            "text": text,
            "likes": safe_int(
                review.get("likes"),
                0,
            ),
            "sentiment": sentiment,
            "source": "google",
            "platform": "google",
        }

    except Exception as e:
        logger.warning(
            f"NORMALIZATION FAILED => {e}"
        )

        return None

# ==========================================================
# DB SAVE
# ==========================================================

def build_review_payload(company_id, review):
    columns = get_review_model_columns()

    payload = {}

    defaults = {
        "company_id": company_id,
        "business_id": company_id,
        "source": "google",
        "platform": "google",
    }

    for column, value in defaults.items():
        if column in columns:
            payload[column] = value

    mapping = {
        "google_review_id": "google_review_id",
        "review_id": "google_review_id",

        "author_name": "author_name",
        "reviewer_name": "author_name",

        "rating": "rating",
        "stars": "rating",

        "review_date": "review_date",
        "google_review_time": "google_review_time",

        "text": "text",
        "review_text": "text",
        "content": "text",

        "likes": "likes",
        "sentiment": "sentiment",
    }

    for db_column, source_key in mapping.items():
        if db_column in columns:
            value = review.get(source_key)

            if value is not None:
                payload[db_column] = value

    return payload


async def save_reviews_to_db(
    company_id,
    reviews,
):
    if not reviews:
        return 0

    saved = 0

    async with AsyncSessionLocal() as db:
        try:
            existing_ids = (
                await load_existing_review_ids(
                    company_id
                )
            )

            for review in reviews:
                review_id = str(
                    review.get("google_review_id")
                )

                if review_id in existing_ids:
                    continue

                payload = build_review_payload(
                    company_id,
                    review,
                )

                db.add(Review(**payload))

                existing_ids.add(review_id)

                saved += 1

            await db.commit()

            logger.info(
                f"DB SAVE COMPLETE => {saved}"
            )

            return saved

        except Exception as e:
            await db.rollback()

            logger.exception(
                f"DB SAVE FAILED => {e}"
            )

            return 0

# ==========================================================
# CRAWL4AI SCRAPER
# ==========================================================

@retry(
    stop=stop_after_attempt(2),
    wait=wait_random_exponential(
        multiplier=2,
        max=10,
    ),
)
async def scrape_crawl4ai_reviews(
    place_id,
    existing_ids=None,
    target_limit=100,
    start_date=None,
    end_date=None,
):
    reviews = []

    existing_ids = existing_ids or set()

    if not ENABLE_CRAWL4AI:
        return []

    try:
        url = (
            "https://www.google.com/maps/search/"
            f"?api=1&query=Google&query_place_id={place_id}"
        )

        proxy = get_random_proxy()

        crawler_config = {
            "headless": True,
            "user_agent": get_user_agent(),
        }

        if proxy:
            crawler_config["proxy"] = proxy

        async with AsyncWebCrawler(
            **crawler_config
        ) as crawler:

            result = await crawler.arun(
                url=url,
                bypass_cache=True,
                word_count_threshold=10,
            )

            if not result:
                return []

            html = result.html

            if not html:
                return []

            parser = HTMLParser(html)

            seen = set()

            cards = parser.css(
                "div[data-review-id]"
            )

            logger.info(
                f"CRAWL4AI CARDS => {len(cards)}"
            )

            for card in cards:
                try:
                    author_node = card.css_first(
                        ".d4r55"
                    )

                    text_node = (
                        card.css_first(
                            ".wiI7pd"
                        )
                        or card.css_first(
                            ".MyEned"
                        )
                    )

                    date_node = card.css_first(
                        ".rsqaWe"
                    )

                    author = clean_text(
                        author_node.text()
                        if author_node
                        else "Anonymous"
                    )

                    text = clean_text(
                        text_node.text()
                        if text_node
                        else ""
                    )

                    review_date = clean_text(
                        date_node.text()
                        if date_node
                        else ""
                    )

                    rating = 5

                    normalized = normalize_review(
                        {
                            "author": author,
                            "text": text,
                            "rating": rating,
                            "date": review_date,
                        },
                        existing_ids,
                        seen,
                        start_date,
                        end_date,
                    )

                    if not normalized:
                        continue

                    reviews.append(normalized)

                    if len(reviews) >= target_limit:
                        break

                except Exception:
                    continue

        logger.info(
            f"CRAWL4AI REVIEWS => {len(reviews)}"
        )

        return reviews

    except Exception as e:
        logger.exception(
            f"CRAWL4AI FAILED => {e}"
        )

        return []

# ==========================================================
# PLAYWRIGHT FALLBACK
# ==========================================================

@retry(
    stop=stop_after_attempt(2),
    wait=wait_random_exponential(
        multiplier=2,
        max=10,
    ),
)
async def playwright_backup(
    place_id,
    existing_ids=None,
    target_limit=50,
    start_date=None,
    end_date=None,
):
    reviews = []

    existing_ids = existing_ids or set()

    browser = None
    context = None

    try:
        async with async_playwright() as p:

            launch_options = {
                "headless": HEADLESS,
                "args": [
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-gpu",
                ],
            }

            if PROXY_SERVER:
                launch_options["proxy"] = {
                    "server": f"http://{PROXY_SERVER}",
                }

                if (
                    PROXY_USERNAME
                    and PROXY_PASSWORD
                ):
                    launch_options["proxy"][
                        "username"
                    ] = PROXY_USERNAME

                    launch_options["proxy"][
                        "password"
                    ] = PROXY_PASSWORD

            browser = await p.chromium.launch(
                **launch_options
            )

            context = await browser.new_context(
                user_agent=get_user_agent(),
                locale="en-US",
                viewport={
                    "width": 1366,
                    "height": 768,
                },
            )

            page = await context.new_page()

            await stealth_async(page)

            url = (
                "https://www.google.com/maps/search/"
                f"?api=1&query=Google&query_place_id={place_id}"
            )

            await page.goto(
                url,
                wait_until="networkidle",
                timeout=PLAYWRIGHT_TIMEOUT,
            )

            await page.wait_for_timeout(5000)

            for _ in range(MAX_SCROLLS):
                try:
                    await page.mouse.wheel(
                        0,
                        random.randint(
                            1000,
                            3000,
                        ),
                    )

                    await page.wait_for_timeout(
                        random.randint(
                            1000,
                            2000,
                        )
                    )

                except Exception:
                    pass

            cards = page.locator(
                "div[data-review-id]"
            )

            count = await cards.count()

            logger.info(
                f"PLAYWRIGHT CARDS => {count}"
            )

            seen = set()

            for i in range(count):
                try:
                    card = cards.nth(i)

                    author = ""

                    try:
                        author = clean_text(
                            await card.locator(
                                ".d4r55"
                            ).inner_text()
                        )

                    except Exception:
                        author = "Anonymous"

                    text = ""

                    for selector in [
                        ".wiI7pd",
                        ".MyEned",
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

                    try:
                        review_date = clean_text(
                            await card.locator(
                                ".rsqaWe"
                            ).inner_text()
                        )

                    except Exception:
                        review_date = ""

                    rating = 5

                    normalized = normalize_review(
                        {
                            "author": author,
                            "text": text,
                            "rating": rating,
                            "date": review_date,
                        },
                        existing_ids,
                        seen,
                        start_date,
                        end_date,
                    )

                    if not normalized:
                        continue

                    reviews.append(normalized)

                    if len(reviews) >= target_limit:
                        break

                except Exception:
                    continue

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
            if context:
                await context.close()

        except Exception:
            pass

        try:
            if browser:
                await browser.close()

        except Exception:
            pass

# ==========================================================
# SERPAPI FALLBACK
# ==========================================================

@retry(
    stop=stop_after_attempt(3),
    wait=wait_random_exponential(
        multiplier=2,
        max=15,
    ),
)
async def scrape_serpapi_reviews(
    place_id,
    existing_ids=None,
    target_limit=100,
    start_date=None,
    end_date=None,
):
    reviews = []

    existing_ids = existing_ids or set()

    if not SERPAPI_KEY:
        return []

    try:
        headers = {
            "User-Agent": get_user_agent(),
            "Accept": "application/json",
        }

        proxy_url = get_random_proxy()

        client_kwargs = {
            "timeout": REQUEST_TIMEOUT,
            "headers": headers,
        }

        if proxy_url:
            client_kwargs["proxy"] = proxy_url

        async with httpx.AsyncClient(
            **client_kwargs
        ) as client:

            params = {
                "engine": "google_maps_reviews",
                "api_key": SERPAPI_KEY,
                "hl": "en",
                "sort_by": "newestFirst",
            }

            if (
                place_id.startswith("0x")
                or ":0x" in place_id
            ):
                params["data_id"] = place_id

            else:
                params["place_id"] = place_id

            response = await client.get(
                "https://serpapi.com/search.json",
                params=params,
            )

            if response.status_code != 200:
                return []

            data = response.json()

            raw_reviews = (
                data.get("reviews", [])
                or []
            )

            seen = set()

            for raw_review in raw_reviews:
                normalized = normalize_review(
                    {
                        "author": (
                            raw_review.get(
                                "user",
                                {},
                            ).get(
                                "name"
                            )
                        ),
                        "text": (
                            raw_review.get(
                                "snippet"
                            )
                        ),
                        "rating": (
                            raw_review.get(
                                "rating"
                            )
                        ),
                        "date": (
                            raw_review.get(
                                "date"
                            )
                        ),
                        "review_id": (
                            raw_review.get(
                                "review_id"
                            )
                        ),
                    },
                    existing_ids,
                    seen,
                    start_date,
                    end_date,
                )

                if not normalized:
                    continue

                reviews.append(normalized)

                if len(reviews) >= target_limit:
                    break

        logger.info(
            f"SERPAPI REVIEWS => {len(reviews)}"
        )

        return reviews

    except Exception as e:
        logger.exception(
            f"SERPAPI FAILED => {e}"
        )

        return []

# ==========================================================
# MAIN SCRAPER
# ==========================================================

async def scrape_google_reviews(
    place_id,
    company_id=None,
    target_limit=100,
    start_date=None,
    end_date=None,
    save_to_database=True,
):
    logger.info(
        f"HYBRID SCRAPER STARTED => {place_id}"
    )

    try:
        existing_review_ids = set()

        if company_id:
            existing_review_ids = (
                await load_existing_review_ids(
                    company_id
                )
            )

        # ==================================================
        # LEVEL 1
        # CRAWL4AI
        # ==================================================

        reviews = await scrape_crawl4ai_reviews(
            place_id=place_id,
            existing_ids=existing_review_ids,
            target_limit=target_limit,
            start_date=start_date,
            end_date=end_date,
        )

        # ==================================================
        # LEVEL 2
        # PLAYWRIGHT
        # ==================================================

        if (
            len(reviews) < target_limit
            and ENABLE_PLAYWRIGHT_FALLBACK
        ):
            remaining = (
                target_limit - len(reviews)
            )

            logger.info(
                f"PLAYWRIGHT FALLBACK => {remaining}"
            )

            playwright_reviews = (
                await playwright_backup(
                    place_id=place_id,
                    existing_ids=existing_review_ids,
                    target_limit=remaining,
                    start_date=start_date,
                    end_date=end_date,
                )
            )

            reviews.extend(playwright_reviews)

        # ==================================================
        # LEVEL 3
        # SERPAPI
        # ==================================================

        if len(reviews) < target_limit:
            remaining = (
                target_limit - len(reviews)
            )

            logger.info(
                f"SERPAPI FALLBACK => {remaining}"
            )

            serp_reviews = (
                await scrape_serpapi_reviews(
                    place_id=place_id,
                    existing_ids=existing_review_ids,
                    target_limit=remaining,
                    start_date=start_date,
                    end_date=end_date,
                )
            )

            reviews.extend(serp_reviews)

        # ==================================================
        # REMOVE DUPLICATES
        # ==================================================

        final_reviews = []

        seen = set()

        for review in reviews:
            review_id = str(
                review.get(
                    "google_review_id"
                )
            )

            if not review_id:
                continue

            if review_id in seen:
                continue

            seen.add(review_id)

            final_reviews.append(review)

        logger.info(
            f"FINAL REVIEW COUNT => {len(final_reviews)}"
        )

        # ==================================================
        # SAVE TO DB
        # ==================================================

        if (
            save_to_database
            and company_id
        ):
            saved = await save_reviews_to_db(
                company_id,
                final_reviews,
            )

            logger.info(
                f"DB SAVED => {saved}"
            )

        return final_reviews

    except Exception as e:
        logger.exception(
            f"MAIN SCRAPER FAILED => {e}"
        )

        return []

    finally:
        gc.collect()
