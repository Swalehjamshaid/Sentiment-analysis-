# ==========================================================
# FILE: app/services/scraper.py
# REVIEW INTEL AI — ENTERPRISE HYBRID SCRAPER
# UPDATED DB-SAFE VERSION — MAY 2026
# ==========================================================

import os
import re
import gc
import random
import asyncio
import hashlib
import logging

from datetime import datetime, timedelta

import httpx

from playwright.async_api import async_playwright
from fake_useragent import UserAgent

from tenacity import (
    retry,
    stop_after_attempt,
    wait_random_exponential,
)

from sqlalchemy import select
from sqlalchemy.inspection import inspect as sa_inspect

# ==========================================================
# DATABASE
# ==========================================================

from app.core.db import AsyncSessionLocal

# ==========================================================
# MODELS
# ==========================================================

from app.core.models import Review

# ==========================================================
# LOGGER
# ==========================================================

logger = logging.getLogger("app.services.scraper")

# ==========================================================
# ENV
# ==========================================================

SERPAPI_KEY = os.getenv("SERPAPI_KEY")

PROXY_SERVER = os.getenv("PROXY_SERVER")
PROXY_USERNAME = os.getenv("PROXY_USERNAME")
PROXY_PASSWORD = os.getenv("PROXY_PASSWORD")

# ==========================================================
# CONFIG
# ==========================================================

REQUEST_TIMEOUT = 120
PLAYWRIGHT_TIMEOUT = 70000
HEADLESS = True
MAX_SCROLLS = 30

# ==========================================================
# USER AGENT
# ==========================================================

def get_user_agent():
    try:
        return UserAgent().random
    except Exception:
        return (
            "Mozilla/5.0 "
            "(Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/126.0 Safari/537.36"
        )

# ==========================================================
# CLEAN TEXT
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

# ==========================================================
# HASH GENERATOR
# ==========================================================

def generate_hash(author, text):
    raw = f"{author}_{text}"

    return hashlib.md5(
        raw.encode("utf-8")
    ).hexdigest()

# ==========================================================
# SAFE INTEGER
# ==========================================================

def safe_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default

# ==========================================================
# DATE PARSER
# ==========================================================

def parse_relative_date(relative_text):
    try:
        if not relative_text:
            return datetime.utcnow()

        text = str(relative_text).lower()
        now = datetime.utcnow()

        if "just now" in text or "today" in text:
            return now

        if "yesterday" in text:
            return now - timedelta(days=1)

        match = re.search(r"(\d+)", text)

        number = int(match.group(1)) if match else 1

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

# ==========================================================
# PROXY
# ==========================================================

def build_proxy_url():
    try:
        if not PROXY_SERVER:
            return None

        if PROXY_USERNAME and PROXY_PASSWORD:
            return f"http://{PROXY_USERNAME}:{PROXY_PASSWORD}@{PROXY_SERVER}"

        return f"http://{PROXY_SERVER}"

    except Exception:
        return None


PROXY_POOL = [
    build_proxy_url()
]


def get_random_proxy():
    try:
        proxies = [proxy for proxy in PROXY_POOL if proxy]
        return random.choice(proxies) if proxies else None
    except Exception:
        return None

# ==========================================================
# EXISTING IDS
# ==========================================================

async def load_existing_review_ids(company_id: int):
    existing = set()

    try:
        async with AsyncSessionLocal() as db:
            stmt = select(
                Review.google_review_id
            ).where(
                Review.company_id == company_id
            )

            result = await db.execute(stmt)
            rows = result.fetchall()

            for row in rows:
                if row[0]:
                    existing.add(row[0])

        logger.info(f"✅ EXISTING IDS => {len(existing)}")
        return existing

    except Exception as e:
        logger.exception(f"❌ EXISTING IDS FAILED => {e}")
        return set()

# ==========================================================
# NORMALIZE REVIEW
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
            review.get("user", {}).get("name", "")
        )

        if not author:
            author = "Anonymous"

        text = clean_text(
            review.get("snippet", "")
        )

        if not text:
            return None

        if len(text) < 10:
            return None

        rating = safe_int(
            review.get("rating", 5),
            5,
        )

        rating = max(1, min(rating, 5))

        review_date = clean_text(
            review.get("date", "")
        )

        review_datetime = parse_relative_date(review_date)

        if start_date and review_datetime < start_date:
            return None

        if end_date and review_datetime > end_date:
            return None

        google_review_id = generate_hash(author, text)

        if google_review_id in seen or google_review_id in existing_ids:
            return None

        seen.add(google_review_id)
        existing_ids.add(google_review_id)

        sentiment = "positive" if rating >= 4 else "negative"

        return {
            "google_review_id": google_review_id,
            "author_name": author,
            "rating": rating,
            "review_date": review_date,
            "google_review_time": review_datetime,
            "text": text,
            "likes": safe_int(review.get("likes", 0)),
            "sentiment": sentiment,
        }

    except Exception as e:
        logger.warning(f"⚠️ NORMALIZE FAILED => {e}")
        return None

# ==========================================================
# REVIEW MODEL SAFE PAYLOAD
# ==========================================================

def get_review_model_columns():
    try:
        return {
            column.key
            for column in sa_inspect(Review).mapper.column_attrs
        }
    except Exception as e:
        logger.exception(f"❌ REVIEW MODEL INSPECT FAILED => {e}")
        return set()


def build_review_payload(company_id: int, review: dict):
    columns = get_review_model_columns()

    payload = {}

    if "company_id" in columns:
        payload["company_id"] = company_id

    field_aliases = {
        "google_review_id": [
            "google_review_id",
            "review_id",
        ],
        "author_name": [
            "author_name",
            "reviewer_name",
            "author",
            "name",
        ],
        "rating": [
            "rating",
            "stars",
        ],
        "review_date": [
            "review_date",
            "date",
        ],
        "google_review_time": [
            "google_review_time",
            "review_datetime",
            "created_at_google",
        ],
        "text": [
            "text",
            "review_text",
            "content",
            "comment",
        ],
        "likes": [
            "likes",
            "helpful_count",
        ],
        "sentiment": [
            "sentiment",
        ],
    }

    for model_field, possible_keys in field_aliases.items():
        if model_field not in columns:
            continue

        for key in possible_keys:
            value = review.get(key)

            if value is not None:
                payload[model_field] = value
                break

    return payload

# ==========================================================
# SAVE REVIEWS TO DATABASE
# ==========================================================

async def save_reviews_to_db(company_id: int, reviews: list[dict]):
    if not company_id:
        logger.error("❌ COMPANY ID MISSING — CANNOT SAVE REVIEWS")
        return 0

    if not reviews:
        logger.info("⚠️ NO REVIEWS TO SAVE")
        return 0

    saved_count = 0

    async with AsyncSessionLocal() as db:
        try:
            existing_ids = await load_existing_review_ids(company_id)

            for review in reviews:
                google_review_id = (
                    review.get("google_review_id")
                    or review.get("review_id")
                )

                if not google_review_id:
                    continue

                if google_review_id in existing_ids:
                    continue

                payload = build_review_payload(
                    company_id=company_id,
                    review=review,
                )

                if "google_review_id" in get_review_model_columns():
                    payload["google_review_id"] = google_review_id

                if not payload:
                    continue

                db_review = Review(**payload)

                db.add(db_review)

                existing_ids.add(google_review_id)
                saved_count += 1

            await db.commit()

            logger.info(f"✅ REVIEWS SAVED TO DB => {saved_count}")
            return saved_count

        except Exception as e:
            await db.rollback()
            logger.exception(f"❌ SAVE REVIEWS FAILED => {e}")
            return 0

# ==========================================================
# SERPAPI SCRAPER
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
        logger.error("❌ SERPAPI KEY MISSING")
        return []

    try:
        proxy_url = get_random_proxy()

        client_kwargs = {
            "timeout": REQUEST_TIMEOUT,
            "headers": {
                "User-Agent": get_user_agent(),
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "*/*",
                "Connection": "keep-alive",
            },
        }

        if proxy_url:
            client_kwargs["proxy"] = proxy_url

        async with httpx.AsyncClient(**client_kwargs) as client:
            next_page_token = None
            fetched = 0
            seen = set()

            while fetched < target_limit:
                params = {
                    "engine": "google_maps",
                    "place_id": place_id,
                    "api_key": SERPAPI_KEY,
                    "hl": "en",
                    "gl": "us",
                }

                if next_page_token:
                    params["next_page_token"] = next_page_token

                logger.info(f"🚀 SERPAPI REQUEST => {fetched}")

                response = await client.get(
                    "https://serpapi.com/search.json",
                    params=params,
                )

                logger.info(f"✅ SERP STATUS => {response.status_code}")

                if response.status_code != 200:
                    logger.warning(
                        f"⚠️ SERP STATUS => {response.status_code} | {response.text[:500]}"
                    )
                    break

                data = response.json()

                logger.info(f"🚀 RESPONSE KEYS => {list(data.keys())}")

                if "error" in data:
                    logger.error(f"❌ SERPAPI ERROR => {data['error']}")
                    return []

                raw_reviews = (
                    data.get("reviews", [])
                    or data.get("place_results", {}).get("reviews", [])
                )

                logger.info(f"📦 SERPAPI RAW => {len(raw_reviews)}")

                if not raw_reviews:
                    break

                for review in raw_reviews:
                    normalized = normalize_review(
                        review=review,
                        existing_ids=existing_ids,
                        seen=seen,
                        start_date=start_date,
                        end_date=end_date,
                    )

                    if not normalized:
                        continue

                    reviews.append(normalized)
                    fetched += 1

                    if fetched >= target_limit:
                        break

                next_page_token = data.get(
                    "serpapi_pagination", {}
                ).get(
                    "next_page_token"
                )

                if not next_page_token:
                    break

                await asyncio.sleep(
                    random.uniform(1, 3)
                )

        logger.info(f"✅ SERPAPI REVIEWS => {len(reviews)}")
        return reviews

    except Exception as e:
        logger.exception(f"❌ SERPAPI FAILED => {e}")
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
            browser = await p.chromium.launch(
                headless=HEADLESS,
                proxy=(
                    {
                        "server": f"http://{PROXY_SERVER}",
                        "username": PROXY_USERNAME,
                        "password": PROXY_PASSWORD,
                    }
                    if PROXY_SERVER
                    else None
                ),
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--disable-setuid-sandbox",
                    "--single-process",
                    "--no-zygote",
                    "--disable-web-security",
                    "--no-sandbox",
                ],
            )

            context = await browser.new_context(
                user_agent=get_user_agent(),
                locale="en-US",
            )

            page = await context.new_page()

            await page.route(
                "**/*.{png,jpg,jpeg,gif,svg,webp}",
                lambda route: route.abort(),
            )

            url = (
                "https://www.google.com/maps/place/"
                f"?q=place_id:{place_id}"
            )

            logger.info(f"🚀 PLAYWRIGHT STARTED => {place_id}")

            await page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=PLAYWRIGHT_TIMEOUT,
            )

            await asyncio.sleep(5)

            try:
                button = page.locator(
                    'button[jsaction*="pane.reviewChart.moreReviews"]'
                )

                if await button.count() > 0:
                    await button.first.click()
                    await asyncio.sleep(5)

            except Exception:
                pass

            review_feed = page.locator('div[role="feed"]')

            for _ in range(MAX_SCROLLS):
                try:
                    await review_feed.evaluate(
                        "(el) => el.scrollTop = el.scrollHeight"
                    )

                    await page.mouse.wheel(
                        0,
                        random.randint(1000, 3000),
                    )

                    await asyncio.sleep(
                        random.uniform(1, 2)
                    )

                except Exception:
                    pass

            cards = page.locator("div[data-review-id]")
            count = await cards.count()

            logger.info(f"📦 PLAYWRIGHT CARDS => {count}")

            seen = set()

            for i in range(count):
                try:
                    card = cards.nth(i)

                    author = clean_text(
                        await card.locator(".d4r55").inner_text()
                    )

                    text = ""

                    try:
                        text = clean_text(
                            await card.locator(
                                'span[jsname="bN97Pc"]'
                            ).inner_text()
                        )
                    except Exception:
                        try:
                            text = clean_text(
                                await card.locator(".MyEned").inner_text()
                            )
                        except Exception:
                            pass

                    if not text:
                        continue

                    review_date = ""

                    try:
                        review_date = clean_text(
                            await card.locator(".rsqaWe").inner_text()
                        )
                    except Exception:
                        pass

                    rating = 5

                    try:
                        aria = await card.locator(
                            ".kvMYJc"
                        ).get_attribute(
                            "aria-label"
                        )

                        match = re.search(r"(\d)", str(aria))

                        if match:
                            rating = int(match.group(1))

                    except Exception:
                        pass

                    normalized = normalize_review(
                        review={
                            "user": {
                                "name": author,
                            },
                            "snippet": text,
                            "rating": rating,
                            "date": review_date,
                        },
                        existing_ids=existing_ids,
                        seen=seen,
                        start_date=start_date,
                        end_date=end_date,
                    )

                    if not normalized:
                        continue

                    reviews.append(normalized)

                    if len(reviews) >= target_limit:
                        break

                except Exception as card_error:
                    logger.warning(f"⚠️ CARD FAILED => {card_error}")
                    continue

        logger.info(f"✅ PLAYWRIGHT REVIEWS => {len(reviews)}")
        return reviews

    except Exception as e:
        logger.exception(f"❌ PLAYWRIGHT FAILED => {e}")
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
# MAIN SCRAPER
# ==========================================================

async def scrape_google_reviews(
    place_id: str,
    company_id: int = None,
    target_limit: int = 100,
    start_date=None,
    end_date=None,
    save_to_database: bool = True,
):
    logger.info(f"🚀 HYBRID SCRAPER STARTED => {place_id}")

    try:
        if not place_id:
            logger.error("❌ PLACE ID MISSING")
            return []

        existing_review_ids = set()

        if company_id:
            existing_review_ids = await load_existing_review_ids(
                company_id
            )

        # ==================================================
        # SERPAPI
        # ==================================================

        serp_reviews = await scrape_serpapi_reviews(
            place_id=place_id,
            existing_ids=existing_review_ids,
            target_limit=target_limit,
            start_date=start_date,
            end_date=end_date,
        )

        # ==================================================
        # PLAYWRIGHT FALLBACK
        # ==================================================

        if len(serp_reviews) < target_limit:
            remaining = target_limit - len(serp_reviews)

            logger.warning(f"⚠️ PLAYWRIGHT FALLBACK => {remaining}")

            playwright_reviews = await playwright_backup(
                place_id=place_id,
                existing_ids=existing_review_ids,
                target_limit=remaining,
                start_date=start_date,
                end_date=end_date,
            )

            serp_reviews.extend(playwright_reviews)

        # ==================================================
        # FINAL DEDUP
        # ==================================================

        final_reviews = []
        seen = set()

        for review in serp_reviews:
            rid = (
                review.get("google_review_id")
                or review.get("review_id")
            )

            if rid and rid not in seen and review.get("text"):
                seen.add(rid)
                final_reviews.append(review)

        logger.info(f"✅ FINAL REVIEW COUNT => {len(final_reviews)}")

        # ==================================================
        # DATABASE SAVE
        # ==================================================

        if save_to_database and company_id:
            saved_count = await save_reviews_to_db(
                company_id=company_id,
                reviews=final_reviews,
            )

            logger.info(f"✅ FINAL DB SAVED COUNT => {saved_count}")

        return final_reviews

    except Exception as e:
        logger.exception(f"❌ SCRAPER FAILED => {e}")
        return []

    finally:
        gc.collect()
