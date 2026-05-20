# ==========================================================
# FILE: app/services/scraper.py
# ENTERPRISE GOOGLE REVIEW SCRAPER
# APIFY PRIMARY + PLAYWRIGHT FALLBACK
# ==========================================================

import os
import re
import asyncio
import hashlib
import logging
import traceback
import random

from datetime import datetime
from typing import Dict, Any

from bs4 import BeautifulSoup
from fake_useragent import UserAgent

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

logger = logging.getLogger(
    "app.services.scraper"
)

# ==========================================================
# ENV
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

APIFY_TOKEN = os.getenv(
    "APIFY_TOKEN"
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

        author_name = safe_string(
            author_name
        )

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

            await asyncio.sleep(8)

            # ==================================================
            # GOOGLE CONSENT
            # ==================================================

            try:

                consent_buttons = [

                    'button:has-text("Accept all")',

                    'button:has-text("I agree")',

                    'button:has-text("Accept")'
                ]

                for selector in consent_buttons:

                    try:

                        button = await page.query_selector(
                            selector
                        )

                        if button:

                            await button.click()

                            logger.info(
                                "✅ Consent accepted"
                            )

                            await asyncio.sleep(3)

                            break

                    except Exception:
                        pass

            except Exception:
                pass

            # ==================================================
            # OPEN REVIEWS
            # ==================================================

            selectors = [

                'button[jsaction*="pane.reviewChart.moreReviews"]',

                'button[aria-label*=" reviews"]',

                'button[aria-label*=" Reviews"]',

                'button[data-tab-index="1"]',

                'button[role="tab"]',

                'div[role="button"][aria-label*="reviews"]'
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

                        logger.info(
                            f"✅ Opened reviews using {selector}"
                        )

                        break

                except Exception:
                    pass

            if not opened:

                logger.warning(
                    "⚠️ Could not open reviews panel"
                )

            await asyncio.sleep(5)

            # ==================================================
            # SCROLL
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
            # HTML
            # ==================================================

            html = await page.content()

            with open(
                "debug_google.html",
                "w",
                encoding="utf-8"
            ) as f:

                f.write(html)

            await page.screenshot(
                path="debug_google.png",
                full_page=True
            )

            logger.info(
                "✅ DEBUG FILES SAVED"
            )

            # ==================================================
            # CAPTCHA DETECTION
            # ==================================================

            captcha_keywords = [

                "unusual traffic",

                "captcha",

                "detected unusual traffic",

                "not a robot"
            ]

            html_lower = html.lower()

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

                or

                soup.select("div[data-review-id]")

                or

                soup.select("div.MyEned")

                or

                soup.select('div[role="article"]')
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

                    rating_elem = (

                        block.select_one("span.kvMYJc")

                        or

                        block.select_one(
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

                        reviews.append(
                            review
                        )

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
