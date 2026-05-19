# ==========================================================
# TRUSTLYTICS - ADVANCED PRODUCTION SCRAPER
# APIFY → PLAYWRIGHT → SERPER FALLBACK
# POSTGRESQL + DASHBOARD SYNC
# ==========================================================

import os
import re
import json
import asyncio
import logging
import random

from datetime import datetime, timezone
from typing import Optional, List, Dict

import requests

from apify_client import ApifyClient

from crawlee.crawlers import (
    PlaywrightCrawler,
    PlaywrightCrawlingContext
)

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from playwright.async_api import async_playwright

from app.core.models import (
    Company,
    Review
)

# ==========================================================
# LOGGER
# ==========================================================

logger = logging.getLogger("app.scraper")

# ==========================================================
# ENV VARIABLES
# ==========================================================

APIFY_API_TOKEN = os.getenv("APIFY_API_TOKEN")

SERPER_API_KEY = os.getenv("SERPER_API_KEY")

PROXY_SERVER = os.getenv("PROXY_SERVER")

PROXY_USERNAME = os.getenv("PROXY_USERNAME")

PROXY_PASSWORD = os.getenv("PROXY_PASSWORD")

# ==========================================================
# APIFY
# ==========================================================

apify_client = ApifyClient(
    APIFY_API_TOKEN
)

# ==========================================================
# HELPERS
# ==========================================================

def utc_now_naive():

    return datetime.now(
        timezone.utc
    ).replace(
        tzinfo=None
    )

def safe_int(value, default=0):

    try:
        return int(value)

    except:
        return default

def safe_float(value, default=0.0):

    try:
        return float(value)

    except:
        return default

def safe_parse_iso_datetime(date_str):

    if not date_str:
        return utc_now_naive()

    try:

        parsed = datetime.fromisoformat(
            date_str.replace(
                "Z",
                "+00:00"
            )
        )

        return parsed.replace(
            tzinfo=None
        )

    except Exception:

        return utc_now_naive()

# ==========================================================
# PROXY CONFIG
# ==========================================================

def build_proxy():

    if not PROXY_SERVER:
        return None

    proxy = {
        "server": PROXY_SERVER
    }

    if PROXY_USERNAME:
        proxy["username"] = PROXY_USERNAME

    if PROXY_PASSWORD:
        proxy["password"] = PROXY_PASSWORD

    logger.info(
        f"✅ Proxy Enabled: {PROXY_SERVER}"
    )

    return proxy

# ==========================================================
# BLOCK HEAVY RESOURCES
# ==========================================================

async def block_resources(route):

    blocked = [

        "image",
        "media",
        "font",
        "stylesheet",
        "websocket"
    ]

    if route.request.resource_type in blocked:

        await route.abort()

    else:

        await route.continue_()

# ==========================================================
# REVIEW PARSER
# ==========================================================

async def parse_review_card(card, idx):

    try:

        review_id = await card.get_attribute(
            "data-review-id"
        )

        author = "Anonymous"

        rating = 5

        text = ""

        try:

            author_locator = card.locator(
                ".d4r55"
            )

            if await author_locator.count() > 0:

                author = (
                    await author_locator.first.inner_text()
                ).strip()

        except:
            pass

        try:

            rating_locator = card.locator(
                'span[role="img"]'
            )

            if await rating_locator.count() > 0:

                aria = await rating_locator.first.get_attribute(
                    "aria-label"
                )

                match = re.search(
                    r"(\d)",
                    aria or ""
                )

                if match:
                    rating = int(
                        match.group(1)
                    )

        except:
            pass

        try:

            text_locator = card.locator(
                ".wiI7pd"
            )

            if await text_locator.count() > 0:

                text = (
                    await text_locator.first.inner_text()
                ).strip()

        except:
            pass

        return {

            "google_review_id":
                review_id or f"crawl_{idx}",

            "author_name":
                author,

            "rating":
                rating,

            "text":
                text,

            "review_text":
                text,

            "google_review_time":
                utc_now_naive(),

            "review_likes":
                0
        }

    except Exception as e:

        logger.error(
            f"❌ Review parse failed: {e}"
        )

        return None

# ==========================================================
# PLAYWRIGHT SCRAPER
# ==========================================================

async def fetch_reviews_with_playwright(

    google_maps_url: str,

    limit: int = 300
):

    logger.info(
        "🚀 Starting Playwright scraper"
    )

    reviews = []

    proxy = build_proxy()

    launch_options = {

        "headless": True,

        "args": [

            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
            "--disable-setuid-sandbox",
            "--disable-background-networking",
            "--disable-sync",
            "--disable-gpu",
            "--disable-extensions",
            "--disable-infobars",
            "--mute-audio",
            "--disable-popup-blocking",
            "--disable-notifications",
            "--no-sandbox"
        ]
    }

    if proxy:
        launch_options["proxy"] = proxy

    crawler = PlaywrightCrawler(

        headless=True,

        max_requests_per_crawl=1,

        browser_launch_options=launch_options
    )

    @crawler.router.default_handler
    async def request_handler(
        context: PlaywrightCrawlingContext
    ):

        page = context.page

        try:

            await page.route(
                "**/*",
                block_resources
            )

            await page.goto(

                google_maps_url,

                wait_until="domcontentloaded",

                timeout=60000
            )

            await page.wait_for_timeout(5000)

            try:

                review_button = page.locator(
                    'button[jsaction*="pane.reviewChart.moreReviews"]'
                )

                if await review_button.count() > 0:

                    await review_button.first.click()

                    await page.wait_for_timeout(5000)

            except:
                pass

            review_cards = page.locator(
                'div[data-review-id]'
            )

            previous_count = 0

            for _ in range(20):

                await page.mouse.wheel(
                    0,
                    7000
                )

                await page.wait_for_timeout(
                    random.randint(
                        1000,
                        2500
                    )
                )

                current_count = await review_cards.count()

                logger.info(
                    f"📦 Loaded: {current_count}"
                )

                if current_count == previous_count:
                    break

                previous_count = current_count

            count = await review_cards.count()

            tasks = [

                parse_review_card(
                    review_cards.nth(i),
                    i
                )

                for i in range(
                    min(count, limit)
                )
            ]

            parsed = await asyncio.gather(
                *tasks
            )

            reviews.extend([
                r for r in parsed if r
            ])

        except Exception as e:

            logger.error(
                f"❌ Playwright scraping failed: {e}"
            )

    await crawler.run([
        google_maps_url
    ])

    logger.info(
        f"✅ Playwright collected {len(reviews)} reviews"
    )

    return reviews

# ==========================================================
# APIFY SCRAPER
# ==========================================================

async def fetch_reviews_from_apify(

    google_maps_url: str,

    target_limit: int = 300
):

    logger.info(
        "⚡ Starting APIFY scraper"
    )

    run_input = {

        "startUrls": [
            {
                "url": google_maps_url
            }
        ],

        "maxReviews":
            target_limit,

        "reviewsSort":
            "newest",

        "reviewsOrigin":
            "google",

        "language":
            "en"
    }

    run = await asyncio.to_thread(

        lambda:
        apify_client.actor(
            "compass~google-maps-reviews-scraper"
        ).call(
            run_input=run_input
        )
    )

    dataset_id = run.get(
        "defaultDatasetId"
    )

    if not dataset_id:

        raise Exception(
            "No APIFY dataset"
        )

    dataset_items = await asyncio.to_thread(

        lambda:
        apify_client.dataset(
            dataset_id
        ).list_items().items
    )

    logger.info(
        f"📦 APIFY returned {len(dataset_items)} reviews"
    )

    reviews = []

    for idx, item in enumerate(
        dataset_items
    ):

        try:

            reviews.append({

                "google_review_id":
                    item.get(
                        "reviewId"
                    ) or f"apify_{idx}",

                "author_name":
                    item.get(
                        "name",
                        "Anonymous"
                    ),

                "rating":
                    safe_float(
                        item.get(
                            "stars",
                            5
                        )
                    ),

                "text":
                    item.get(
                        "text",
                        ""
                    ),

                "review_text":
                    item.get(
                        "text",
                        ""
                    ),

                "google_review_time":
                    safe_parse_iso_datetime(
                        item.get(
                            "publishedAtDate"
                        )
                    ),

                "review_likes":
                    safe_int(
                        item.get(
                            "likesCount",
                            0
                        )
                    )
            })

        except Exception as parse_error:

            logger.error(
                f"❌ APIFY parse error: {parse_error}"
            )

    return reviews

# ==========================================================
# SERPER FALLBACK
# ==========================================================

async def fetch_from_serper(

    company_name: str,

    limit: int = 50
):

    logger.warning(
        "⚠️ Using Serper fallback"
    )

    if not SERPER_API_KEY:
        return []

    try:

        response = await asyncio.to_thread(

            lambda:
            requests.post(

                "https://google.serper.dev/search",

                headers={

                    "X-API-KEY":
                        SERPER_API_KEY,

                    "Content-Type":
                        "application/json"
                },

                data=json.dumps({

                    "q":
                        f"{company_name} reviews",

                    "gl":
                        "pk",

                    "hl":
                        "en"
                }),

                timeout=30
            )
        )

        data = response.json()

        reviews = []

        for idx, item in enumerate(
            data.get("organic", [])
        ):

            if len(reviews) >= limit:
                break

            reviews.append({

                "google_review_id":
                    f"serper_{idx}",

                "author_name":
                    item.get(
                        "title",
                        "Anonymous"
                    ),

                "rating":
                    5,

                "text":
                    item.get(
                        "snippet",
                        ""
                    ),

                "review_text":
                    item.get(
                        "snippet",
                        ""
                    ),

                "google_review_time":
                    utc_now_naive(),

                "review_likes":
                    0
            })

        return reviews

    except Exception as e:

        logger.error(
            f"❌ Serper failed: {e}"
        )

        return []

# ==========================================================
# MAIN GOOGLE SCRAPER
# ==========================================================

async def fetch_reviews_from_google(

    place_id: Optional[str] = None,

    company_id: Optional[int] = None,

    session: Optional[AsyncSession] = None,

    target_limit: int = 300
):

    try:

        company_name = "Business"

        if session and company_id:

            company_stmt = select(
                Company
            ).where(
                Company.id == company_id
            )

            company_result = await session.execute(
                company_stmt
            )

            company = company_result.scalars().first()

            if company:

                company_name = company.name

                place_id = (
                    place_id
                    or company.google_place_id
                )

        if not place_id:

            logger.error(
                "❌ Missing Google Place ID"
            )

            return []

        google_maps_url = (
            f"https://www.google.com/maps/place/?q=place_id:{place_id}"
        )

        logger.info(
            f"📍 URL: {google_maps_url}"
        )

        # ==================================================
        # APIFY FIRST
        # ==================================================

        try:

            reviews = await fetch_reviews_from_apify(

                google_maps_url=
                    google_maps_url,

                target_limit=
                    target_limit
            )

            if reviews:

                logger.info(
                    f"✅ APIFY success: {len(reviews)}"
                )

                return reviews

        except Exception as apify_error:

            logger.error(
                f"❌ APIFY failed: {apify_error}"
            )

        # ==================================================
        # PLAYWRIGHT FALLBACK
        # ==================================================

        try:

            reviews = await fetch_reviews_with_playwright(

                google_maps_url=
                    google_maps_url,

                limit=
                    target_limit
            )

            if reviews:

                logger.info(
                    f"✅ Playwright success: {len(reviews)}"
                )

                return reviews

        except Exception as playwright_error:

            logger.error(
                f"❌ Playwright failed: {playwright_error}"
            )

        # ==================================================
        # SERPER FALLBACK
        # ==================================================

        return await fetch_from_serper(

            company_name=
                company_name,

            limit=
                target_limit
        )

    except Exception as main_error:

        logger.error(
            f"❌ Main scraper failed: {main_error}"
        )

        return []

# ==========================================================
# REVIEW SERVICE
# ==========================================================

class ReviewService:

    # ======================================================
    # INGEST REVIEWS
    # ======================================================

    @staticmethod
    async def ingest_from_google(

        company_id: int,

        session: AsyncSession
    ):

        try:

            company_stmt = select(
                Company
            ).where(
                Company.id == company_id
            )

            company_result = await session.execute(
                company_stmt
            )

            company = company_result.scalars().first()

            if not company:

                return {

                    "status":
                        "error",

                    "message":
                        "Company not found"
                }

            reviews = await fetch_reviews_from_google(

                place_id=
                    company.google_place_id,

                company_id=
                    company_id,

                session=
                    session,

                target_limit=
                    300
            )

            inserted_count = 0

            for item in reviews:

                try:

                    duplicate_stmt = select(
                        Review
                    ).where(
                        Review.google_review_id
                        ==
                        item.get(
                            "google_review_id"
                        )
                    )

                    duplicate_result = await session.execute(
                        duplicate_stmt
                    )

                    existing = (
                        duplicate_result
                        .scalars()
                        .first()
                    )

                    if existing:
                        continue

                    new_review = Review(

                        company_id=
                            company_id,

                        google_review_id=
                            item.get(
                                "google_review_id"
                            ),

                        author_name=
                            item.get(
                                "author_name",
                                "Anonymous"
                            ),

                        rating=
                            item.get(
                                "rating",
                                5
                            ),

                        text=
                            item.get(
                                "text",
                                ""
                            ),

                        google_review_time=
                            item.get(
                                "google_review_time",
                                utc_now_naive()
                            ),

                        first_seen_at=
                            utc_now_naive(),

                        review_likes=
                            item.get(
                                "review_likes",
                                0
                            )
                    )

                    session.add(
                        new_review
                    )

                    inserted_count += 1

                except Exception as save_error:

                    logger.error(
                        f"❌ Save failed: {save_error}"
                    )

            await session.commit()

            logger.info(
                f"✅ Stored {inserted_count} reviews"
            )

            return {

                "status":
                    "success",

                "ingested_count":
                    inserted_count
            }

        except Exception as e:

            await session.rollback()

            logger.exception(
                "❌ Ingestion failed"
            )

            return {

                "status":
                    "error",

                "message":
                    str(e)
            }

    # ======================================================
    # DASHBOARD LOADER
    # ======================================================

    @staticmethod
    async def get_latest_reviews(

        company_id: int,

        limit: int = 100,

        session: Optional[AsyncSession] = None
    ):

        try:

            if not session:
                return []

            stmt = (

                select(Review)

                .where(
                    Review.company_id == company_id
                )

                .order_by(
                    Review.google_review_time.desc()
                )

                .limit(limit)
            )

            result = await session.execute(
                stmt
            )

            reviews = result.scalars().all()

            formatted = []

            for review in reviews:

                formatted.append({

                    "id":
                        review.id,

                    "author_name":
                        review.author_name,

                    "rating":
                        review.rating,

                    "text":
                        review.text,

                    "review_text":
                        review.text,

                    "created_at":
                        (
                            review.google_review_time.isoformat()
                            if review.google_review_time
                            else None
                        ),

                    "review_likes":
                        review.review_likes
                })

            return formatted

        except Exception:

            logger.exception(
                "❌ Dashboard review load failed"
            )

            return []
