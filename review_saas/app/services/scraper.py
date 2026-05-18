# ==========================================================
# HIGH PERFORMANCE REVIEW INTELLIGENCE SCRAPER
# OPTIMIZED FOR:
# - SPEED
# - GOOGLE MAPS STABILITY
# - LOWER RAM USAGE
# - PROXY SUPPORT
# - FASTAPI ASYNC
# - APIFY + CRAWLEE + SERPER FALLBACK
# ==========================================================

import os
import re
import json
import asyncio
import logging
import random
import requests

from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

from apify_client import ApifyClient

from crawlee.crawlers import (
    PlaywrightCrawler,
    PlaywrightCrawlingContext
)

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Company, Review

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

USE_PROXY_SCRAPER_FIRST = (
    os.getenv(
        "USE_PROXY_SCRAPER_FIRST",
        "true"
    ).lower() == "true"
)

# ==========================================================
# APIFY CLIENT
# ==========================================================

apify_client = ApifyClient(APIFY_API_TOKEN)

# ==========================================================
# DATETIME HELPERS
# ==========================================================

def utc_now_naive() -> datetime:
    return datetime.utcnow().replace(tzinfo=None)

def safe_parse_iso_datetime(
    date_str: Optional[str]
) -> datetime:

    if not date_str:
        return utc_now_naive()

    try:

        parsed = datetime.fromisoformat(
            date_str.replace("Z", "+00:00")
        )

        return parsed.replace(tzinfo=None)

    except Exception:
        return utc_now_naive()

# ==========================================================
# PROXY CONFIG
# ==========================================================

def build_proxy_config():

    if not PROXY_SERVER:
        logger.warning("⚠️ PROXY_SERVER missing")
        return None

    proxy_config = {
        "server": PROXY_SERVER
    }

    if PROXY_USERNAME:
        proxy_config["username"] = PROXY_USERNAME

    if PROXY_PASSWORD:
        proxy_config["password"] = PROXY_PASSWORD

    logger.info(f"✅ Proxy Enabled: {PROXY_SERVER}")

    return proxy_config

# ==========================================================
# RESOURCE BLOCKER
# ==========================================================

async def block_resources(route):

    resource_type = route.request.resource_type

    if resource_type in [
        "image",
        "media",
        "font",
        "stylesheet"
    ]:
        await route.abort()

    else:
        await route.continue_()

# ==========================================================
# FAST REVIEW PARSER
# ==========================================================

async def parse_review_card(card, index: int):

    try:

        review_id = await card.get_attribute(
            "data-review-id"
        )

        author = "Anonymous"
        rating = 5
        text = ""

        try:

            author_locator = card.locator(".d4r55")

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

                rating_text = await rating_locator.first.get_attribute(
                    "aria-label"
                )

                match = re.search(
                    r"(\\d)",
                    rating_text or ""
                )

                if match:
                    rating = int(match.group(1))

        except:
            pass

        try:

            text_locator = card.locator(".wiI7pd")

            if await text_locator.count() > 0:

                text = (
                    await text_locator.first.inner_text()
                ).strip()

        except:
            pass

        return {

            "google_review_id":
                review_id or f"crawl_{index}",

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
# CRAWLEE SCRAPER
# ==========================================================

async def fetch_reviews_with_crawlee(
    google_maps_url: str,
    limit: int = 300
):

    logger.info(
        "🚀 Starting Optimized Crawlee Scraper"
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
            "--no-sandbox"
        ]
    }

    proxy_config = build_proxy_config()

    if proxy_config:
        launch_options["proxy"] = proxy_config

    crawler = PlaywrightCrawler(

        headless=True,

        max_requests_per_crawl=1,

        max_concurrency=1,

        request_handler_timeout=120,

        browser_launch_options=launch_options
    )

    @crawler.router.default_handler
    async def request_handler(
        context: PlaywrightCrawlingContext
    ):

        page = context.page

        try:

            logger.info(
                f"🌐 Opening Google Maps"
            )

            await page.route(
                "**/*",
                block_resources
            )

            await page.goto(

                google_maps_url,

                wait_until="domcontentloaded",

                timeout=45000
            )

            await page.wait_for_timeout(
                random.randint(1000, 2500)
            )

            try:

                review_button = page.locator(
                    'button[jsaction*="pane.reviewChart.moreReviews"]'
                )

                if await review_button.count() > 0:

                    await review_button.first.click()

                    await page.wait_for_timeout(
                        random.randint(1000, 2500)
                    )

            except Exception as e:

                logger.warning(
                    f"⚠️ Failed opening reviews: {e}"
                )

            review_cards = page.locator(
                'div[data-review-id]'
            )

            previous_count = 0

            for _ in range(10):

                await page.mouse.wheel(
                    0,
                    5000
                )

                await page.wait_for_timeout(
                    random.randint(800, 1800)
                )

                current_count = await review_cards.count()

                logger.info(
                    f"📦 Reviews Loaded: {current_count}"
                )

                if current_count == previous_count:
                    break

                previous_count = current_count

            count = await review_cards.count()

            logger.info(
                f"✅ Final Reviews Found: {count}"
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

            results = await asyncio.gather(*tasks)

            reviews.extend([
                r for r in results if r
            ])

        except Exception as e:

            logger.error(
                f"❌ Crawlee failed: {e}"
            )

    await crawler.run([google_maps_url])

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

    logger.info("⚡ Starting APIFY Scraper")

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

    return dataset_items

# ==========================================================
# SERPER FALLBACK
# ==========================================================

async def fetch_from_serper_fallback(
    company_name: str,
    limit: int = 50
):

    logger.warning(
        f"⚠️ Using Serper fallback"
    )

    if not SERPER_API_KEY:
        return []

    try:

        response = await asyncio.to_thread(

            lambda:
            requests.post(

                "https://google.serper.dev/search",

                headers={
                    "X-API-KEY": SERPER_API_KEY,
                    "Content-Type": "application/json"
                },

                data=json.dumps({
                    "q": f"{company_name} reviews",
                    "gl": "pk",
                    "hl": "en"
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
                    item.get("title", "Anonymous"),

                "rating":
                    5,

                "text":
                    item.get("snippet", ""),

                "google_review_time":
                    utc_now_naive(),

                "review_likes":
                    0
            })

        logger.info(
            f"✅ Serper collected {len(reviews)}"
        )

        return reviews

    except Exception as e:

        logger.error(
            f"❌ Serper failed: {e}"
        )

        return []

# ==========================================================
# MAIN FETCHER
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

        if session and company_id:

            stmt = select(
                Review.google_review_id
            ).where(
                Review.company_id == company_id
            )

            result = await session.execute(stmt)

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
        # APIFY FIRST (FASTEST)
        # ==================================================

        try:

            dataset_items = await fetch_reviews_from_apify(
                google_maps_url=google_maps_url,
                target_limit=target_limit
            )

            for idx, review in enumerate(dataset_items):

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
                            int(
                                review.get("stars", 5)
                            ),

                        "text":
                            (
                                review.get("text")
                                or ""
                            ),

                        "google_review_time":
                            safe_parse_iso_datetime(
                                review.get("publishedAtDate")
                            ),

                        "review_likes":
                            review.get(
                                "likesCount",
                                0
                            )
                    })

                    if len(all_reviews) >= target_limit:
                        break

                except Exception:
                    continue

            if all_reviews:

                logger.info(
                    f"✅ APIFY Success: {len(all_reviews)}"
                )

                return all_reviews

        except Exception as apify_error:

            logger.error(
                f"❌ APIFY failed: {apify_error}"
            )

        # ==================================================
        # CRAWLEE FALLBACK
        # ==================================================

        if USE_PROXY_SCRAPER_FIRST:

            try:

                crawlee_reviews = await fetch_reviews_with_crawlee(
                    google_maps_url=google_maps_url,
                    limit=target_limit
                )

                if crawlee_reviews:
                    return crawlee_reviews

            except Exception as crawlee_error:

                logger.error(
                    f"❌ Crawlee failed: {crawlee_error}"
                )

        # ==================================================
        # SERPER LAST FALLBACK
        # ==================================================

        return await fetch_from_serper_fallback(
            company_name,
            limit=target_limit
        )

    except Exception as main_error:

        logger.error(
            f"❌ Main fetch failed: {main_error}"
        )

        return []

# ==========================================================
# REVIEW SERVICE
# ==========================================================

class ReviewService:

    @staticmethod
    async def get_latest_reviews(
        company_id: int,
        limit: int = 300
    ):

        from app.core.db import AsyncSessionLocal

        async with AsyncSessionLocal() as session:

            try:

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

                result = await session.execute(stmt)

                reviews = result.scalars().all()

                return [

                    {

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
                            review.google_review_time.isoformat()
                            if review.google_review_time
                            else None,

                        "review_likes":
                            review.review_likes,

                        "sentiment":
                            (
                                "positive"
                                if review.rating >= 4
                                else "negative"
                                if review.rating <= 2
                                else "neutral"
                            )
                    }

                    for review in reviews
                ]

            except Exception:

                logger.exception(
                    "❌ Failed loading reviews"
                )

                return []

    @staticmethod
    async def ingest_from_google(
        company_id: int
    ):

        from app.core.db import AsyncSessionLocal

        async with AsyncSessionLocal() as session:

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
                    raise Exception("Company not found")

                reviews = await fetch_reviews_from_google(

                    place_id=company.google_place_id,

                    company_id=company_id,

                    session=session,

                    target_limit=300
                )

                if not reviews:

                    return {
                        "status": "success",
                        "ingested_count": 0
                    }

                stmt = select(
                    Review.google_review_id
                ).where(
                    Review.company_id == company_id
                )

                result = await session.execute(stmt)

                existing_ids = set(
                    result.scalars().all()
                )

                ingested_count = 0

                for item in reviews:

                    try:

                        if item["google_review_id"] in existing_ids:
                            continue

                        new_review = Review(

                            company_id=company_id,

                            google_review_id=item.get(
                                "google_review_id"
                            ),

                            author_name=item.get(
                                "author_name",
                                "Anonymous"
                            ),

                            rating=item.get(
                                "rating",
                                5
                            ),

                            text=item.get(
                                "text",
                                ""
                            ),

                            google_review_time=item.get(
                                "google_review_time",
                                utc_now_naive()
                            ),

                            first_seen_at=utc_now_naive(),

                            review_likes=item.get(
                                "review_likes",
                                0
                            )
                        )

                        session.add(new_review)

                        ingested_count += 1

                    except Exception as e:

                        logger.error(
                            f"❌ Save failed: {e}"
                        )

                await session.commit()

                return {

                    "status":
                        "success",

                    "ingested_count":
                        ingested_count
                }

            except Exception as e:

                await session.rollback()

                logger.exception(
                    "❌ Ingest failed"
                )

                return {

                    "status":
                        "error",

                    "message":
                        str(e),

                    "ingested_count":
                        0
                }
