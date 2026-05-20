# ==========================================================
# FILE: app/services/scraper.py
# ENTERPRISE GOOGLE REVIEW SCRAPER
# APIFY PRIMARY + PLAYWRIGHT FALLBACK
# RAILWAY SAFE VERSION
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

from bs4 import BeautifulSoup

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

from playwright.async_api import (
    async_playwright,
    TimeoutError as PlaywrightTimeoutError
)

from apify_client import ApifyClient

# ==========================================================
# MODELS
# ==========================================================

from app.core.models import (
    Review,
    Company
)

# ==========================================================
# LOGGER
# ==========================================================

logger = logging.getLogger("app.services.scraper")

# ==========================================================
# ENV
# ==========================================================

PROXY_SERVER = os.getenv(
    "PROXY_SERVER",
    "http://gw.dataimpulse.com:823"
)

PROXY_USERNAME = os.getenv(
    "PROXY_USERNAME"
)

PROXY_PASSWORD = os.getenv(
    "PROXY_PASSWORD"
)

APIFY_TOKEN = os.getenv(
    "APIFY_TOKEN"
)

HEADLESS = True

# ==========================================================
# USER AGENTS
# ==========================================================

USER_AGENTS = [

    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",

    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",

    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
]

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

    @staticmethod
    async def get_total_reviews(
        db: AsyncSession,
        company_id: int
    ):

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

    @staticmethod
    async def get_average_rating(
        db: AsyncSession,
        company_id: int
    ):

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

    text = safe_string(text)

    text = text.replace("\n", " ")
    text = text.replace("\r", " ")
    text = text.replace("\t", " ")

    text = " ".join(text.split())

    return text[:5000]


def generate_hash(author, text):

    raw = f"{author}_{text}"

    return hashlib.md5(
        raw.encode("utf-8")
    ).hexdigest()


def normalize_rating(text):

    try:

        match = re.search(
            r"([0-9.]+)",
            str(text)
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
# APIFY
# ==========================================================

def create_apify_client():

    if not APIFY_TOKEN:

        logger.warning(
            "⚠️ APIFY_TOKEN missing"
        )

        return None

    return ApifyClient(
        APIFY_TOKEN
    )

# ==========================================================
# GOOGLE URL
# ==========================================================

def build_google_maps_url(
    place_id: str
):

    place_id = str(place_id).strip()

    return (
        f"https://www.google.com/maps/place/?q=place_id:{place_id}"
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
# NORMALIZE
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
            or "Anonymous"
        )

        author_name = safe_string(author_name)

        review_text = (
            item.get("text")
            or item.get("review")
            or item.get("comment")
            or ""
        )

        review_text = clean_review_text(
            review_text
        )

        if not review_text:

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

        review_date = (
            item.get("publishedAtDate")
            or item.get("date")
        )

        review_date = safe_datetime(
            review_date
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

            "google_review_time": review_date,

            "review_likes": 0,

            "sentiment_score": sentiment_score
        }

    except Exception as e:

        logger.exception(
            f"❌ Normalize failed: {e}"
        )

        return None

# ==========================================================
# APIFY SCRAPER
# ==========================================================

async def apify_scraper(
    google_maps_url: str,
    target_limit: int = 100
):

    try:

        logger.info(
            "🚀 APIFY SCRAPER STARTED"
        )

        client = create_apify_client()

        if not client:

            return []

        run_input = {

            "startUrls": [
                {
                    "url": google_maps_url
                }
            ],

            "maxReviews": target_limit,

            "reviewsSort": "newest",

            "language": "en"
        }

        run = client.actor(
            "compass/google-maps-reviews-scraper"
        ).call(
            run_input=run_input
        )

        dataset_id = run["defaultDatasetId"]

        items = list(

            client.dataset(
                dataset_id
            ).iterate_items()
        )

        logger.info(
            f"✅ APIFY REVIEWS: {len(items)}"
        )

        return items

    except Exception as e:

        logger.exception(
            f"❌ APIFY FAILED: {e}"
        )

        return []

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
        "🚀 PLAYWRIGHT FALLBACK STARTED"
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
                "--disable-setuid-sandbox",
                "--no-sandbox",
            ]
        )

        context = await browser.new_context(

            viewport={
                "width": 1400,
                "height": 900,
            },

            user_agent=random.choice(USER_AGENTS),

            locale="en-US"
        )

        page = await context.new_page()

        try:

            await page.goto(
                google_maps_url,
                wait_until="networkidle",
                timeout=120000
            )

            await asyncio.sleep(8)

            try:

                buttons = [

                    'button:has-text("Accept all")',

                    'button:has-text("I agree")',

                    'button:has-text("Accept")'
                ]

                for selector in buttons:

                    try:

                        btn = await page.query_selector(selector)

                        if btn:

                            await btn.click()

                            await asyncio.sleep(2)

                            break

                    except Exception:
                        pass

            except Exception:
                pass

            selectors = [

                'button[jsaction*="pane.reviewChart.moreReviews"]',

                'button[aria-label*=" reviews"]',

                'button[aria-label*=" Reviews"]'
            ]

            opened = False

            for selector in selectors:

                try:

                    button = await page.wait_for_selector(
                        selector,
                        timeout=10000
                    )

                    if button:

                        await button.click()

                        opened = True

                        break

                except Exception:
                    pass

            await asyncio.sleep(5)

            if not opened:

                logger.warning(
                    "⚠️ Reviews panel not opened"
                )

            previous_height = 0
            retries = 0

            while retries < 8:

                await page.mouse.wheel(
                    0,
                    5000
                )

                await asyncio.sleep(3)

                current_height = await page.evaluate(
                    """
                    () => {
                        const feed = document.querySelector('div[role="feed"]');
                        return feed ? feed.scrollHeight : 0;
                    }
                    """
                )

                if current_height == previous_height:

                    retries += 1

                else:

                    retries = 0

                previous_height = current_height

            html = await page.content()

            html_lower = html.lower()

            captcha_keywords = [

                "unusual traffic",

                "captcha",

                "not a robot"
            ]

            for keyword in captcha_keywords:

                if keyword in html_lower:

                    logger.warning(
                        f"⚠️ CAPTCHA DETECTED: {keyword}"
                    )

                    return []

            soup = BeautifulSoup(
                html,
                "lxml"
            )

            review_blocks = (

                soup.select("div.jftiEf")

                or soup.select("div[data-review-id]")

                or soup.select('div[role="article"]')
            )

            logger.info(
                f"📦 PLAYWRIGHT REVIEWS FOUND: {len(review_blocks)}"
            )

            for block in review_blocks[:target_limit]:

                try:

                    reviewer = (

                        block.select_one(".d4r55")

                        or block.select_one(".TSUbDb")
                    )

                    reviewer_name = (

                        reviewer.text.strip()

                        if reviewer else "Anonymous"
                    )

                    review_text_elem = (

                        block.select_one(".wiI7pd")

                        or block.select_one(".MyEned")
                    )

                    review_text = (

                        review_text_elem.text.strip()

                        if review_text_elem else ""
                    )

                    rating_elem = (

                        block.select_one("span.kvMYJc")

                        or block.select_one(
                            "span[aria-label*='star']"
                        )
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
                        f"❌ Parse failed: {row_error}"
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
# SAVE REVIEWS
# ==========================================================

async def save_reviews(
    db: AsyncSession,
    company_id: int,
    reviews: List[Dict]
):

    inserted = 0

    existing = await get_existing_reviews(
        db,
        company_id
    )

    for item in reviews:

        try:

            normalized = normalize_review(
                item,
                company_id
            )

            if not normalized:
                continue

            review_id = normalized[
                "google_review_id"
            ]

            if review_id in existing:
                continue

            review = Review(

                company_id=company_id,

                google_review_id=normalized[
                    "google_review_id"
                ],

                author_name=normalized[
                    "author_name"
                ],

                rating=normalized[
                    "rating"
                ],

                text=normalized[
                    "text"
                ],

                google_review_time=normalized[
                    "google_review_time"
                ],

                review_likes=normalized[
                    "review_likes"
                ],

                sentiment_score=normalized[
                    "sentiment_score"
                ]
            )

            db.add(review)

            inserted += 1

        except Exception as e:

            logger.exception(
                f"❌ SAVE FAILED: {e}"
            )

    try:

        await db.commit()

    except Exception as e:

        logger.exception(
            f"❌ DB COMMIT FAILED: {e}"
        )

        await db.rollback()

    return inserted

# ==========================================================
# MAIN SCRAPER
# ==========================================================

async def scrape_google_reviews(
    db: AsyncSession,
    company_id: int,
    place_id: str,
    target_limit: int = 100
):

    logger.info(
        "🚀 GOOGLE REVIEW SCRAPER STARTED"
    )

    try:

        google_maps_url = build_google_maps_url(
            place_id
        )

        reviews = []

        # ==================================================
        # APIFY PRIMARY
        # ==================================================

        try:

            reviews = await apify_scraper(
                google_maps_url,
                target_limit
            )

        except Exception as e:

            logger.exception(
                f"❌ APIFY PRIMARY FAILED: {e}"
            )

        # ==================================================
        # PLAYWRIGHT FALLBACK
        # ==================================================

        if not reviews:

            logger.warning(
                "⚠️ FALLING BACK TO PLAYWRIGHT"
            )

            reviews = await playwright_scraper(
                google_maps_url,
                target_limit
            )

        if not reviews:

            logger.warning(
                "⚠️ NO REVIEWS FOUND"
            )

            return {

                "success": False,

                "inserted": 0,

                "total_scraped": 0,

                "reviews": []
            }

        inserted = await save_reviews(
            db,
            company_id,
            reviews
        )

        logger.info(
            f"✅ INSERTED REVIEWS: {inserted}"
        )

        return {

            "success": True,

            "inserted": inserted,

            "total_scraped": len(reviews),

            "reviews": reviews
        }

    except Exception as e:

        logger.exception(
            f"❌ MAIN SCRAPER FAILED: {e}"
        )

        traceback.print_exc()

        return {

            "success": False,

            "inserted": 0,

            "total_scraped": 0,

            "reviews": [],

            "error": str(e)
        }

# ==========================================================
# COMPANY SCRAPER
# ==========================================================

async def sync_company_reviews(
    db: AsyncSession,
    company: Company,
    target_limit: int = 100
):

    try:

        if not company.place_id:

            logger.warning(
                "⚠️ COMPANY PLACE ID MISSING"
            )

            return {

                "success": False,

                "error": "Missing place_id"
            }

        result = await scrape_google_reviews(

            db=db,

            company_id=company.id,

            place_id=company.place_id,

            target_limit=target_limit
        )

        return result

    except Exception as e:

        logger.exception(
            f"❌ COMPANY SYNC FAILED: {e}"
        )

        return {

            "success": False,

            "error": str(e)
        }
