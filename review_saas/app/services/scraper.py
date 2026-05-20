# ==========================================================
# FILE: app/services/scraper.py
# TRUSTLYTICS AI SAAS
# ENTERPRISE GOOGLE REVIEWS SCRAPER
# PLAYWRIGHT + RESIDENTIAL PROXY + APIFY FALLBACK
# FULL RAILWAY PRODUCTION VERSION
# ==========================================================

import os
import re
import asyncio
import hashlib
import logging
import traceback
import random

from datetime import datetime
from typing import Dict, Any, List

import aiohttp
import httpx

from bs4 import BeautifulSoup
from fake_useragent import UserAgent
from selectolax.parser import HTMLParser

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential
)

from sqlalchemy import (
    select,
    func,
    desc
)

from sqlalchemy.ext.asyncio import AsyncSession

from apify_client import ApifyClient

from playwright.async_api import (
    async_playwright,
    TimeoutError as PlaywrightTimeoutError
)

from app.core.models import (
    Review,
    Company
)

# ==========================================================
# SAFE SETTINGS IMPORT
# ==========================================================

try:

    from app.core.config import settings

except Exception:

    class settings:

        APIFY_TOKEN = None

# ==========================================================
# LOGGER
# ==========================================================

logger = logging.getLogger(
    "app.services.scraper"
)

# ==========================================================
# ENV VARIABLES
# ==========================================================

PROXY_SERVER = os.getenv(
    "PROXY_SERVER",
    "http://gw.dataimpulse.com:823"
)

PROXY_USERNAME = os.getenv(
    "PROXY_USERNAME",
    "f24ab799ffcf42cf2c54"
)

PROXY_PASSWORD = os.getenv(
    "PROXY_PASSWORD",
    "e25628cf2c1b3ba3"
)

HEADLESS = True

ua = UserAgent()

# ==========================================================
# REVIEW SERVICE
# ==========================================================

class ReviewService:

    @staticmethod
    async def get_latest_reviews(
        db: AsyncSession,
        company_id: int,
        limit: int = 50
    ):

        try:

            stmt = (
                select(Review)
                .where(
                    Review.company_id == company_id
                )
                .order_by(
                    desc(Review.created_at)
                )
                .limit(limit)
            )

            result = await db.execute(stmt)

            return result.scalars().all()

        except Exception as e:

            logger.exception(
                f"❌ get_latest_reviews failed: {e}"
            )

            return []

    @staticmethod
    async def get_total_reviews(
        db: AsyncSession,
        company_id: int
    ):

        try:

            stmt = (
                select(
                    func.count(Review.id)
                )
                .where(
                    Review.company_id == company_id
                )
            )

            result = await db.execute(stmt)

            return result.scalar() or 0

        except Exception:

            return 0

    @staticmethod
    async def get_average_rating(
        db: AsyncSession,
        company_id: int
    ):

        try:

            stmt = (
                select(
                    func.avg(Review.rating)
                )
                .where(
                    Review.company_id == company_id
                )
            )

            result = await db.execute(stmt)

            avg = result.scalar()

            if avg is None:
                return 0

            return round(float(avg), 2)

        except Exception:

            return 0

# ==========================================================
# HELPERS
# ==========================================================

def safe_string(value, default=""):

    try:

        if value is None:
            return default

        return str(value).strip()

    except Exception:

        return default


def safe_int(value, default=0):

    try:

        if value is None:
            return default

        return int(float(value))

    except Exception:

        return default


def safe_datetime(value):

    try:

        if not value:
            return datetime.utcnow()

        if isinstance(value, datetime):

            return value.replace(
                tzinfo=None
            )

        value = str(value)

        value = value.replace(
            "Z",
            "+00:00"
        )

        parsed = datetime.fromisoformat(value)

        return parsed.replace(
            tzinfo=None
        )

    except Exception:

        return datetime.utcnow()


def clean_review_text(text):

    text = safe_string(
        text,
        ""
    )

    text = text.replace("\n", " ")
    text = text.replace("\r", " ")
    text = text.replace("\t", " ")

    text = " ".join(
        text.split()
    )

    if len(text) > 5000:
        text = text[:5000]

    return text


def generate_hash(author, text):

    raw = f"{author}_{text}"

    return hashlib.md5(
        raw.encode("utf-8")
    ).hexdigest()


def normalize_rating(rating_text):

    try:

        match = re.search(
            r"([0-9.]+)",
            str(rating_text)
        )

        if match:

            return int(
                float(
                    match.group(1)
                )
            )

    except Exception:
        pass

    return 5

# ==========================================================
# APIFY CLIENT
# ==========================================================

def create_apify_client():

    token = getattr(
        settings,
        "APIFY_TOKEN",
        None
    )

    if not token:

        logger.warning(
            "⚠️ APIFY_TOKEN missing"
        )

        return None

    return ApifyClient(token)

# ==========================================================
# GOOGLE MAPS URL
# ==========================================================

def build_google_maps_url(
    place_id: str
):

    return (
        "https://www.google.com/maps/search/"
        f"?api=1&query_place_id={place_id}"
    )

# ==========================================================
# EXISTING REVIEWS
# ==========================================================

async def get_existing_reviews(
    session: AsyncSession,
    company_id: int
):

    stmt = (
        select(Review)
        .where(
            Review.company_id == company_id
        )
    )

    result = await session.execute(stmt)

    reviews = result.scalars().all()

    mapped = {}

    for review in reviews:

        mapped[
            review.google_review_id
        ] = review

    return mapped

# ==========================================================
# NORMALIZE REVIEW
# ==========================================================

def normalize_review(
    item: Dict[str, Any],
    company_id: int
):

    try:

        author_name = (
            item.get("name")
            or item.get("reviewerName")
            or item.get("authorName")
            or item.get("userName")
            or item.get("reviewer")
            or "Anonymous"
        )

        author_name = safe_string(
            author_name,
            "Anonymous"
        )

        review_text = (
            item.get("text")
            or item.get("reviewText")
            or item.get("review")
            or item.get("comment")
            or ""
        )

        review_text = clean_review_text(
            review_text
        )

        if not review_text.strip():

            return None

        rating = (
            item.get("stars")
            or item.get("rating")
            or 5
        )

        rating = safe_int(
            rating,
            5
        )

        review_time = (
            item.get("publishedAtDate")
            or item.get("date")
        )

        review_time = safe_datetime(
            review_time
        )

        google_review_id = (
            item.get("reviewId")
            or item.get("id")
        )

        if not google_review_id:

            google_review_id = (
                f"{company_id}_"
                f"{generate_hash(author_name, review_text)}"
            )

        sentiment_score = round(
            rating / 5,
            2
        )

        return {

            "google_review_id": google_review_id,
            "author_name": author_name,
            "rating": rating,
            "text": review_text,
            "google_review_time": review_time,
            "review_likes": 0,
            "sentiment_score": sentiment_score
        }

    except Exception as e:

        logger.exception(
            f"❌ Normalize failed: {e}"
        )

        return None

# ==========================================================
# PLAYWRIGHT SCRAPER
# ==========================================================

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(
        multiplier=2,
        min=2,
        max=10
    )
)
async def playwright_scraper(
    google_maps_url: str,
    target_limit: int = 100
):

    logger.info(
        "🚀 PLAYWRIGHT SCRAPER STARTED"
    )

    reviews = []

    async with async_playwright() as p:

        browser = await p.chromium.launch(

            headless=HEADLESS,

            proxy={
                "server": PROXY_SERVER,
                "username": PROXY_USERNAME,
                "password": PROXY_PASSWORD,
            },

            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--disable-setuid-sandbox",
            ]
        )

        context = await browser.new_context(

            viewport={
                "width": random.randint(1200, 1600),
                "height": random.randint(700, 1000),
            },

            user_agent=ua.random,

            locale="en-US"
        )

        page = await context.new_page()

        try:

            logger.info(
                f"🌐 Opening URL: {google_maps_url}"
            )

            await page.goto(
                google_maps_url,
                wait_until="networkidle",
                timeout=120000
            )

            await asyncio.sleep(
                random.uniform(3, 6)
            )

            # ==================================================
            # SAVE DEBUG HTML
            # ==================================================

            html_before = await page.content()

            with open(
                "debug_before_reviews.html",
                "w",
                encoding="utf-8"
            ) as f:
                f.write(html_before)

            # ==================================================
            # CLICK REVIEW BUTTON
            # ==================================================

            selectors = [

                'button[jsaction*="pane.reviewChart.moreReviews"]',

                'button[aria-label*="reviews"]',

                'button[aria-label*="Reviews"]',

                'button[role="tab"]'
            ]

            opened = False

            for selector in selectors:

                try:

                    button = await page.query_selector(
                        selector
                    )

                    if button:

                        await button.click()

                        opened = True

                        logger.info(
                            f"✅ Review panel opened using: {selector}"
                        )

                        break

                except Exception:
                    pass

            if not opened:

                logger.warning(
                    "⚠️ Could not open review panel"
                )

            await asyncio.sleep(
                random.uniform(3, 5)
            )

            # ==================================================
            # SCROLL ENGINE
            # ==================================================

            previous_height = 0
            retries = 0

            while retries < 8:

                await page.mouse.wheel(
                    0,
                    5000
                )

                await asyncio.sleep(
                    random.uniform(2, 4)
                )

                current_height = await page.evaluate(
                    """
                    () => {
                        const feed = document.querySelector('div[role="feed"]');
                        return feed ? feed.scrollHeight : 0;
                    }
                    """
                )

                logger.info(
                    f"📜 Scroll Height: {current_height}"
                )

                if current_height == previous_height:

                    retries += 1

                else:

                    retries = 0

                previous_height = current_height

            # ==================================================
            # FINAL HTML
            # ==================================================

          # ==========================================================
# SAVE DEBUG HTML + SCREENSHOT
# ==========================================================

html = await page.content()

with open(
    "debug_google.html",
    "w",
    encoding="utf-8"
) as f:

    f.write(html)

logger.info(
    "✅ DEBUG HTML SAVED"
)

await page.screenshot(
    path="debug_google.png",
    full_page=True
)

logger.info(
    "✅ DEBUG SCREENSHOT SAVED"
)

            with open(
                "debug_after_reviews.html",
                "w",
                encoding="utf-8"
            ) as f:
                f.write(html)

            # ==================================================
            # BEAUTIFULSOUP PARSER
            # ==================================================

            soup = BeautifulSoup(
                html,
                "lxml"
            )

            # ==================================================
            # SELECTOLAX PARSER
            # ==================================================

            tree = HTMLParser(html)

            review_blocks = soup.select(
    'div.jftiEf'
)

if not review_blocks:

    review_blocks = soup.select(
        'div[data-review-id]'
    )

if not review_blocks:

    review_blocks = soup.select(
        'div.MyEned'
    )

logger.info(
    f"📦 REVIEW BLOCKS FOUND: {len(review_blocks)}"
)
            logger.info(
                f"📦 PLAYWRIGHT REVIEWS FOUND: {len(review_blocks)}"
            )

            for block in review_blocks[:target_limit]:

                try:

                    reviewer = (

    block.select_one(".d4r55")

    or

    block.select_one(".TSUbDb")
)

                    reviewer_name = (
                        reviewer.text.strip()
                        if reviewer else "Anonymous"
                    )

                  review_text_elem = (

    block.select_one(".wiI7pd")

    or

    block.select_one(".MyEned")

    or

    block.select_one(".OA1nbd")
)

                    review_text = (
                        review_text_elem.text.strip()
                        if review_text_elem else ""
                    )

                    rating_elem = block.select_one(
                        "span.kvMYJc"
                    )

                    rating = 5

                    if rating_elem:

                        rating = normalize_rating(
                            rating_elem.get(
                                "aria-label",
                                ""
                            )
                        )

                    review = {

                        "reviewId":
                            generate_hash(
                                reviewer_name,
                                review_text
                            ),

                        "reviewerName":
                            reviewer_name,

                        "text":
                            review_text,

                        "stars":
                            rating,

                        "publishedAtDate":
                            datetime.utcnow().isoformat()
                    }

                    if review_text:

                        reviews.append(review)

                except Exception as row_error:

                    logger.exception(
                        f"❌ Review parse failed: {row_error}"
                    )

        except PlaywrightTimeoutError:

            logger.error(
                "❌ PLAYWRIGHT TIMEOUT"
            )

        except Exception as e:

            logger.exception(
                f"❌ PLAYWRIGHT FAILED: {e}"
            )

        finally:

            await context.close()
            await browser.close()

    logger.info(
        f"✅ PLAYWRIGHT FINAL REVIEWS: {len(reviews)}"
    )

    return reviews

# ==========================================================
# APIFY FALLBACK
# ==========================================================

async def apify_fallback_scraper(
    google_maps_url: str,
    target_limit: int
):

    logger.info(
        "🚀 APIFY FALLBACK STARTED"
    )

    client = create_apify_client()

    if not client:

        return []

    try:

        actor_input = {

            "startUrls": [
                {
                    "url": google_maps_url
                }
            ],

            "language": "en",

            "maxReviews": target_limit,

            "reviewsSort": "newest",

            "reviewsOrigin": "all",

            "personalData": True,

            "maxImages": 0,

            "maxCrawledPlaces": 1,

            "proxy": {
                "useApifyProxy": True
            }
        }

        run = await asyncio.to_thread(
            client.actor(
                "compass~google-maps-reviews-scraper"
            ).call,
            run_input=actor_input
        )

        dataset_id = run.get(
            "defaultDatasetId"
        )

        if not dataset_id:

            return []

        dataset = client.dataset(
            dataset_id
        )

        raw_reviews = []

        for attempt in range(10):

            dataset_items = await asyncio.to_thread(
                dataset.list_items,
                clean=True,
                limit=target_limit
            )

            raw_reviews = dataset_items.items

            logger.info(
                f"📦 APIFY REVIEWS: {len(raw_reviews)}"
            )

            if raw_reviews:
                break

            await asyncio.sleep(2)

        return raw_reviews

    except Exception as e:

        logger.exception(
            f"❌ APIFY FAILED: {e}"
        )

        return []

# ==========================================================
# MAIN SCRAPER
# ==========================================================

async def fetch_reviews_from_google(

    place_id: str,

    company_id: int,

    session: AsyncSession,

    target_limit: int = 100

):

    logger.info(
        f"🚀 SCRAPER STARTED | company_id={company_id}"
    )

    try:

        existing_reviews = await get_existing_reviews(
            session=session,
            company_id=company_id
        )

        google_maps_url = build_google_maps_url(
            place_id
        )

        logger.info(
            f"🌐 GOOGLE MAPS URL: {google_maps_url}"
        )

        logger.info(
            f"🆔 PLACE ID: {place_id}"
        )

        # ==================================================
        # PRIMARY PLAYWRIGHT SCRAPER
        # ==================================================

        raw_reviews = await playwright_scraper(

            google_maps_url=google_maps_url,

            target_limit=target_limit
        )

        # ==================================================
        # APIFY FALLBACK
        # ==================================================

        if not raw_reviews:

            logger.warning(
                "⚠️ PLAYWRIGHT returned 0 reviews"
            )

            raw_reviews = await apify_fallback_scraper(

                google_maps_url=google_maps_url,

                target_limit=target_limit
            )

        inserted_reviews = []

        inserted_count = 0
        updated_count = 0
        duplicate_count = 0

        memory_hashes = set()

        for item in raw_reviews:

            try:

                normalized = normalize_review(
                    item=item,
                    company_id=company_id
                )

                if not normalized:
                    continue

                google_review_id = normalized[
                    "google_review_id"
                ]

                if google_review_id in memory_hashes:

                    duplicate_count += 1
                    continue

                memory_hashes.add(
                    google_review_id
                )

                existing_review = existing_reviews.get(
                    google_review_id
                )

                if existing_review:

                    duplicate_count += 1
                    continue

                new_review = Review(

                    company_id=company_id,

                    google_review_id=normalized["google_review_id"],

                    author_name=normalized["author_name"],

                    rating=normalized["rating"],

                    sentiment_score=normalized["sentiment_score"],

                    text=normalized["text"],

                    google_review_time=normalized["google_review_time"],

                    review_likes=normalized["review_likes"],

                    first_seen_at=datetime.utcnow(),

                    created_at=datetime.utcnow()
                )

                session.add(
                    new_review
                )

                inserted_reviews.append(
                    normalized
                )

                inserted_count += 1

            except Exception as row_error:

                logger.exception(
                    f"❌ Row failed: {row_error}"
                )

        # ==================================================
        # COMMIT
        # ==================================================

        try:

            logger.info(
                f"🚀 Committing {inserted_count} reviews"
            )

            await session.commit()

            logger.info(
                "✅ Database commit successful"
            )

        except Exception as commit_error:

            await session.rollback()

            logger.exception(
                f"❌ Commit failed: {commit_error}"
            )

        logger.info(
            f"✅ FETCHED: {len(raw_reviews)}"
        )

        logger.info(
            f"✅ INSERTED: {inserted_count}"
        )

        logger.info(
            f"✅ DUPLICATES: {duplicate_count}"
        )

        return {

            "success": True,

            "inserted": inserted_count,

            "updated": updated_count,

            "duplicates": duplicate_count,

            "fetched": len(raw_reviews),

            "reviews": inserted_reviews
        }

    except Exception as e:

        try:
            await session.rollback()

        except Exception:
            pass

        logger.exception(
            f"❌ SCRAPER FAILED: {e}"
        )

        logger.error(
            traceback.format_exc()
        )

        return {

            "success": False,

            "inserted": 0,

            "updated": 0,

            "duplicates": 0,

            "fetched": 0,

            "reviews": [],

            "error": str(e)
        }
