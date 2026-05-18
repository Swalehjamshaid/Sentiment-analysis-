# ==========================================================
# WORLD-CLASS PRODUCTION SCRAPER
# FASTAPI + PLAYWRIGHT + APIFY + GOOGLE MAPS
# ULTRA OPTIMIZED FOR RAILWAY + PROXIES
# ==========================================================

import os
import re
import json
import asyncio
import logging
import random
import requests

from datetime import datetime
from typing import Optional, List, Dict, Any

from apify_client import ApifyClient

from crawlee.crawlers import (
    PlaywrightCrawler,
    PlaywrightCrawlingContext
)

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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

APIFY_API_TOKEN = os.getenv(
    "APIFY_API_TOKEN"
)

SERPER_API_KEY = os.getenv(
    "SERPER_API_KEY"
)

PROXY_SERVER = os.getenv(
    "PROXY_SERVER"
)

PROXY_USERNAME = os.getenv(
    "PROXY_USERNAME"
)

PROXY_PASSWORD = os.getenv(
    "PROXY_PASSWORD"
)

USE_PROXY_SCRAPER_FIRST = (
    os.getenv(
        "USE_PROXY_SCRAPER_FIRST",
        "true"
    ).lower() == "true"
)

# ==========================================================
# APIFY
# ==========================================================

apify_client = ApifyClient(
    APIFY_API_TOKEN
)

# ==========================================================
# HELPERS
# ==========================================================

def utc_now_naive() -> datetime:

    return datetime.utcnow().replace(
        tzinfo=None
    )

def safe_int(value, default=0):

    try:
        return int(value)

    except:
        return default

def safe_parse_iso_datetime(
    date_str
):

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

    except:
        return utc_now_naive()

# ==========================================================
# PROXY
# ==========================================================

def build_proxy_config():

    if not PROXY_SERVER:

        logger.warning(
            "⚠️ PROXY_SERVER missing"
        )

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
# BLOCK RESOURCES
# ==========================================================

async def block_resources(route):

    resource_type = route.request.resource_type

    blocked = [

        "image",
        "media",
        "font",
        "stylesheet",
        "websocket"
    ]

    if resource_type in blocked:

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
        text = ""
        rating = 5

        # ==================================================
        # AUTHOR
        # ==================================================

        try:

            author_locator = card.locator(
                ".d4r55"
            )

            if await author_locator.count() > 0:

                author = (
                    await author_locator
                    .first
                    .inner_text()
                ).strip()

        except:
            pass

        # ==================================================
        # RATING
        # ==================================================

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

        # ==================================================
        # REVIEW TEXT
        # ==================================================

        try:

            text_locator = card.locator(
                ".wiI7pd"
            )

            if await text_locator.count() > 0:

                text = (
                    await text_locator
                    .first
                    .inner_text()
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

async def fetch_reviews_with_crawlee(

    google_maps_url: str,

    limit: int = 300

):

    logger.info(
        "🚀 Starting Crawlee Scraper"
    )

    reviews = []

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
            "--disable-default-apps",
            "--disable-translate",
            "--no-sandbox"
        ]
    }

    proxy_config = build_proxy_config()

    if proxy_config:
        launch_options["proxy"] = proxy_config

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

            logger.info(
                f"🌐 Opening URL: {google_maps_url}"
            )

            # ==============================================
            # BLOCK HEAVY RESOURCES
            # ==============================================

            await page.route(
                "**/*",
                block_resources
            )

            # ==============================================
            # OPEN PAGE
            # ==============================================

            await page.goto(

                google_maps_url,

                wait_until="domcontentloaded",

                timeout=45000
            )

            await page.wait_for_timeout(
                random.randint(
                    1000,
                    2500
                )
            )

            # ==============================================
            # OPEN REVIEWS PANEL
            # ==============================================

            try:

                review_button = page.locator(
                    'button[jsaction*="pane.reviewChart.moreReviews"]'
                )

                if await review_button.count() > 0:

                    await review_button.first.click()

                    await page.wait_for_timeout(
                        random.randint(
                            1500,
                            3000
                        )
                    )

            except Exception as review_button_error:

                logger.warning(
                    f"⚠️ Failed opening reviews panel: {review_button_error}"
                )

            # ==============================================
            # SCROLL REVIEWS
            # ==============================================

            review_cards = page.locator(
                'div[data-review-id]'
            )

            previous_count = 0

            for _ in range(12):

                await page.mouse.wheel(
                    0,
                    6000
                )

                await page.wait_for_timeout(
                    random.randint(
                        800,
                        1600
                    )
                )

                current_count = await review_cards.count()

                logger.info(
                    f"📦 Reviews loaded: {current_count}"
                )

                if current_count == previous_count:
                    break

                previous_count = current_count

            count = await review_cards.count()

            logger.info(
                f"✅ Final review count: {count}"
            )

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
                f"❌ Crawlee failed: {e}"
            )

    await crawler.run([
        google_maps_url
    ])

    logger.info(
        f"✅ Crawlee collected {len(reviews)} reviews"
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
        "⚡ Starting APIFY"
    )

    fetch_limit = target_limit + 20

    run_input = {

        "startUrls": [
            {
                "url": google_maps_url
            }
        ],

        "maxReviews": fetch_limit,

        "reviewsSort": "newest",

        "reviewsOrigin": "google",

        "language": "en"
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
            "No APIFY dataset returned"
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

    return dataset_items

# ==========================================================
# SERPER FALLBACK
# ==========================================================

async def fetch_from_serper_fallback(

    company_name: str,

    limit: int = 50

):

    logger.warning(
        "⚠️ Using Serper fallback"
    )

    if not SERPER_API_KEY:

        logger.error(
            "❌ SERPER_API_KEY missing"
        )

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

                timeout=20
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

                "google_review_time":
                    utc_now_naive(),

                "review_likes":
                    0
            })

        logger.info(
            f"✅ Serper returned {len(reviews)} reviews"
        )

        return reviews

    except Exception as e:

        logger.error(
            f"❌ Serper failed: {e}"
        )

        return []

# ==========================================================
# MAIN SCRAPER
# ==========================================================

async def fetch_reviews_from_google(

    place_id: Optional[str] = None,

    company_id: Optional[int] = None,

    session: Optional[AsyncSession] = None,

    target_limit: int = 300,

    **kwargs

):

    all_reviews = []

    existing_ids = set()

    company_name = "Business"

    try:

        # ==============================================
        # EXISTING IDS
        # ==============================================

        if session and company_id:

            stmt = select(
                Review.google_review_id
            ).where(
                Review.company_id == company_id
            )

            result = await session.execute(
                stmt
            )

            existing_ids = set(
                result.scalars().all()
            )

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

        # ==============================================
        # VALIDATE PLACE ID
        # ==============================================

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

        # ==============================================
        # APIFY FIRST
        # ==============================================

        try:

            dataset_items = await fetch_reviews_from_apify(

                google_maps_url=google_maps_url,

                target_limit=target_limit
            )

            for idx, review in enumerate(
                dataset_items
            ):

                try:

                    review_id = (
                        review.get("reviewId")
                        or f"apify_{idx}"
                    )

                    if review_id in existing_ids:
                        continue

                    all_reviews.append({

                        "google_review_id":
                            review_id,

                        "author_name":
                            (
                                review.get("name")
                                or "Anonymous"
                            ),

                        "rating":
                            safe_int(
                                review.get(
                                    "stars",
                                    5
                                ),
                                5
                            ),

                        "text":
                            (
                                review.get("text")
                                or ""
                            ),

                        "google_review_time":
                            safe_parse_iso_datetime(
                                review.get(
                                    "publishedAtDate"
                                )
                            ),

                        "review_likes":
                            safe_int(
                                review.get(
                                    "likesCount",
                                    0
                                ),
                                0
                            )
                    })

                    if len(all_reviews) >= target_limit:
                        break

                except Exception as parse_error:

                    logger.error(
                        f"❌ APIFY parse failed: {parse_error}"
                    )

            if all_reviews:

                logger.info(
                    f"✅ APIFY success: {len(all_reviews)} reviews"
                )

                return all_reviews

        except Exception as apify_error:

            logger.error(
                f"❌ APIFY failed: {apify_error}"
            )

        # ==============================================
        # PLAYWRIGHT FALLBACK
        # ==============================================

        if USE_PROXY_SCRAPER_FIRST:

            try:

                crawlee_reviews = await fetch_reviews_with_crawlee(

                    google_maps_url=google_maps_url,

                    limit=target_limit
                )

                if crawlee_reviews:

                    logger.info(
                        f"✅ Crawlee success: {len(crawlee_reviews)} reviews"
                    )

                    return crawlee_reviews

            except Exception as crawlee_error:

                logger.error(
                    f"❌ Crawlee error: {crawlee_error}"
                )

        # ==============================================
        # SERPER FINAL FALLBACK
        # ==============================================

        return await fetch_from_serper_fallback(

            company_name=company_name,

            limit=target_limit
        )

    except Exception as main_error:

        logger.error(
            f"❌ Main scraper failed: {main_error}"
        )

        return []
