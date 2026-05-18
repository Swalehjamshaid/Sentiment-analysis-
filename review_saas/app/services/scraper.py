# filename: app/services/scraper.py

# ==========================================================

# REVIEW INTELLIGENCE SCRAPER

# PROXY FIRST + CRAWLEE + PLAYWRIGHT + APIFY + SERPER

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

# ==========================================================

# PROXY SETTINGS

# ==========================================================

PROXY_SERVER = os.getenv("PROXY_SERVER")
PROXY_USERNAME = os.getenv("PROXY_USERNAME")
PROXY_PASSWORD = os.getenv("PROXY_PASSWORD")

USE_PROXY_SCRAPER_FIRST = os.getenv(
"USE_PROXY_SCRAPER_FIRST",
"true"
).lower() == "true"

# ==========================================================

# APIFY CLIENT

# ==========================================================

if not APIFY_API_TOKEN:

```
logger.warning(
    "⚠️ APIFY_API_TOKEN missing"
)
```

apify_client = ApifyClient(APIFY_API_TOKEN)

# ==========================================================

# SAFE UTC DATETIME

# ==========================================================

def utc_now_naive() -> datetime:
return datetime.utcnow().replace(tzinfo=None)

# ==========================================================

# SAFE ISO DATETIME PARSER

# ==========================================================

def safe_parse_iso_datetime(
date_str: Optional[str]
) -> datetime:

```
if not date_str:
    return utc_now_naive()

try:

    parsed = datetime.fromisoformat(
        date_str.replace("Z", "+00:00")
    )

    return parsed.replace(tzinfo=None)

except Exception as e:

    logger.warning(
        f"⚠️ Failed parsing date: {e}"
    )

    return utc_now_naive()
```

# ==========================================================

# RELATIVE DATE PARSER

# ==========================================================

def parse_relative_date(date_text: str) -> datetime:

```
if not date_text:
    return utc_now_naive()

now = utc_now_naive()

match = re.search(r"(\d+)", date_text)

quantity = int(match.group(1)) if match else 1

date_text = date_text.lower()

if "second" in date_text:
    return now - timedelta(seconds=quantity)

if "minute" in date_text:
    return now - timedelta(minutes=quantity)

if "hour" in date_text:
    return now - timedelta(hours=quantity)

if "day" in date_text:
    return now - timedelta(days=quantity)

if "week" in date_text:
    return now - timedelta(weeks=quantity)

if "month" in date_text:
    return now - timedelta(days=quantity * 30)

if "year" in date_text:
    return now - timedelta(days=quantity * 365)

return now
```

# ==========================================================

# SERPER FALLBACK

# ==========================================================

async def fetch_from_serper_fallback(
company_name: str,
limit: int = 300
) -> List[Dict[str, Any]]:

```
logger.warning(
    f"⚠️ Using Serper fallback for {company_name}"
)

if not SERPER_API_KEY:

    logger.error(
        "❌ SERPER_API_KEY missing"
    )

    return []

try:

    url = "https://google.serper.dev/search"

    payload = json.dumps({
        "q": f"{company_name} reviews",
        "gl": "pk",
        "hl": "en"
    })

    headers = {
        "X-API-KEY": SERPER_API_KEY,
        "Content-Type": "application/json"
    }

    response = await asyncio.to_thread(
        lambda: requests.post(
            url,
            headers=headers,
            data=payload,
            timeout=30
        )
    )

    response.raise_for_status()

    data = response.json()

    reviews = []

    for idx, item in enumerate(
        data.get("organic", [])
    ):

        if len(reviews) >= limit:
            break

        reviews.append({

            "google_review_id":
                f"serper_{idx}_{int(datetime.utcnow().timestamp())}",

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
        f"✅ Serper collected {len(reviews)} reviews"
    )

    return reviews

except Exception as e:

    logger.error(
        f"❌ Serper fallback failed: {e}"
    )

    return []
```

# ==========================================================

# BUILD PLAYWRIGHT PROXY CONFIG

# ==========================================================

def build_proxy_config():

```
if not PROXY_SERVER:

    logger.warning(
        "⚠️ PROXY_SERVER missing"
    )

    return None

proxy_config = {
    "server": PROXY_SERVER
}

if PROXY_USERNAME:
    proxy_config["username"] = PROXY_USERNAME

if PROXY_PASSWORD:
    proxy_config["password"] = PROXY_PASSWORD

logger.info(
    f"✅ Proxy enabled: {PROXY_SERVER}"
)

return proxy_config
```

# ==========================================================

# CRAWLEE PLAYWRIGHT PROXY SCRAPER

# ==========================================================

async def fetch_reviews_with_crawlee(
google_maps_url: str,
limit: int = 300
):

```
logger.warning(
    "⚠️ Using Proxy-Based Crawlee Scraper..."
)

reviews = []

launch_options = {
    "headless": True,
    "args": [
        "--disable-blink-features=AutomationControlled",
        "--disable-dev-shm-usage",
        "--no-sandbox",
        "--disable-setuid-sandbox"
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
            f"🌐 Opening: {google_maps_url}"
        )

        await page.goto(
            google_maps_url,
            wait_until="networkidle",
            timeout=120000
        )

        await page.wait_for_timeout(
            random.randint(5000, 9000)
        )

        # ==================================================
        # OPEN REVIEWS PANEL
        # ==================================================

        try:

            review_button = page.locator(
                'button[jsaction*="pane.reviewChart.moreReviews"]'
            )

            if await review_button.count() > 0:

                logger.info(
                    "✅ Opening reviews panel"
                )

                await review_button.first.click()

                await page.wait_for_timeout(
                    random.randint(4000, 8000)
                )

        except Exception as e:

            logger.warning(
                f"⚠️ Failed opening reviews: {e}"
            )

        # ==================================================
        # SCROLL REVIEWS
        # ==================================================

        logger.info(
            "📜 Scrolling reviews..."
        )

        for _ in range(35):

            await page.mouse.wheel(
                0,
                random.randint(5000, 9000)
            )

            await page.wait_for_timeout(
                random.randint(1500, 4000)
            )

        # ==================================================
        # GET REVIEW CARDS
        # ==================================================

        review_cards = page.locator(
            'div[data-review-id]'
        )

        count = await review_cards.count()

        logger.info(
            f"📦 Crawlee found {count} review cards"
        )

        for i in range(min(count, limit)):

            try:

                card = review_cards.nth(i)

                review_id = await card.get_attribute(
                    "data-review-id"
                )

                author = "Anonymous"
                rating = 5
                text = ""

                # ==============================================
                # AUTHOR
                # ==============================================

                try:

                    author_locator = card.locator(
                        '.d4r55'
                    )

                    if await author_locator.count() > 0:

                        author = await author_locator.first.inner_text()

                except:
                    pass

                # ==============================================
                # RATING
                # ==============================================

                try:

                    rating_locator = card.locator(
                        'span[role="img"]'
                    )

                    if await rating_locator.count() > 0:

                        rating_text = await rating_locator.first.get_attribute(
                            "aria-label"
                        )

                        match = re.search(
                            r'(\d)',
                            rating_text or ""
                        )

                        if match:
                            rating = int(match.group(1))

                except:
                    pass

                # ==============================================
                # REVIEW TEXT
                # ==============================================

                try:

                    text_locator = card.locator(
                        '.wiI7pd'
                    )

                    if await text_locator.count() > 0:

                        text = await text_locator.first.inner_text()

                except:
                    pass

                reviews.append({

                    "google_review_id":
                        review_id or f"crawl_{i}",

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
                })

            except Exception as item_error:

                logger.error(
                    f"❌ Crawlee review parse failed: {item_error}"
                )

                continue

    except Exception as e:

        logger.error(
            f"❌ Crawlee failed: {e}"
        )

await crawler.run([google_maps_url])

logger.info(
    f"✅ Crawlee collected {len(reviews)} reviews"
)

return reviews
```

# ==========================================================

# APIFY SCRAPER

# ==========================================================

async def fetch_reviews_from_apify(
google_maps_url: str,
target_limit: int = 300
):

```
logger.warning(
    "⚠️ Switching to APIFY fallback..."
)

fetch_limit = target_limit + 100

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

logger.info(
    f"📦 APIFY INPUT: {run_input}"
)

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
        "No dataset returned from APIFY"
    )

logger.info(
    f"✅ APIFY completed | Dataset: {dataset_id}"
)

dataset_items = await asyncio.to_thread(

    lambda:
    apify_client.dataset(
        dataset_id
    ).list_items().items
)

logger.info(
    f"📦 Total Reviews fetched from APIFY: {len(dataset_items)}"
)

return dataset_items
```

# ==========================================================

# MAIN GOOGLE REVIEW FETCHER

# ==========================================================

async def fetch_reviews_from_google(

```
place_id: Optional[str] = None,

company_id: Optional[int] = None,

session: Optional[AsyncSession] = None,

target_limit: int = 300,

**kwargs
```

) -> List[Dict[str, Any]]:

```
all_reviews: List[Dict[str, Any]] = []

existing_ids = set()

company_name = "Business"

google_maps_url = ""

try:

    # ==================================================
    # LOAD EXISTING IDS
    # ==================================================

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

        logger.info(
            f"✅ Existing reviews in DB: {len(existing_ids)}"
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

    # ==================================================
    # VALIDATE PLACE ID
    # ==================================================

    if not place_id:

        logger.error(
            f"❌ Missing Google Place ID for {company_name}"
        )

        return []

    google_maps_url = (
        f"https://www.google.com/maps/place/?q=place_id:{place_id}"
    )

    logger.info(
        f"📍 Google Maps URL: {google_maps_url}"
    )

    # ==================================================
    # PROXY SCRAPER FIRST
    # ==================================================

    if USE_PROXY_SCRAPER_FIRST:

        try:

            logger.info(
                "🚀 Starting Proxy-Based Crawlee Scraper"
            )

            crawlee_reviews = await fetch_reviews_with_crawlee(
                google_maps_url=google_maps_url,
                limit=target_limit
            )

            if crawlee_reviews:

                logger.info(
                    f"✅ Proxy scraper success: {len(crawlee_reviews)}"
                )

                return crawlee_reviews

        except Exception as crawlee_error:

            logger.error(
                f"❌ Proxy scraper failed: {crawlee_error}"
            )

    # ==================================================
    # APIFY FALLBACK
    # ==================================================

    logger.warning(
        "⚠️ Using APIFY fallback"
    )

    dataset_items = await fetch_reviews_from_apify(
        google_maps_url=google_maps_url,
        target_limit=target_limit
    )

    if not dataset_items:

        raise Exception(
            "APIFY returned empty reviews"
        )

    skipped_duplicates = 0

    # ==================================================
    # PROCESS REVIEWS
    # ==================================================

    for idx, review in enumerate(dataset_items):

        try:

            review_id = (
                review.get("reviewId")
                or f"apify_{idx}_{int(datetime.utcnow().timestamp())}"
            )

            if review_id in existing_ids:
                skipped_duplicates += 1
                continue

            if any(
                r["google_review_id"] == review_id
                for r in all_reviews
            ):
                skipped_duplicates += 1
                continue

            review_text = (
                review.get("text")
                or review.get("reviewText")
                or "No content"
            )

            author_name = (
                review.get("name")
                or review.get("reviewerName")
                or "Anonymous"
            )

            try:
                rating = int(
                    review.get("stars", 5)
                )
            except:
                rating = 5

            review_time = safe_parse_iso_datetime(
                review.get("publishedAtDate")
            )

            likes = review.get(
                "likesCount",
                0
            )

            if likes is None:
                likes = 0

            all_reviews.append({

                "google_review_id": review_id,

                "author_name": author_name,

                "rating": rating,

                "text": review_text,

                "google_review_time": review_time,

                "review_likes": likes
            })

            if len(all_reviews) >= target_limit:
                break

        except Exception as item_error:

            logger.error(
                f"❌ Review processing failed: {item_error}"
            )

            continue

    logger.info(
        f"✅ APIFY collected {len(all_reviews)} reviews"
    )

    logger.info(
        f"⚠️ Duplicate reviews skipped: {skipped_duplicates}"
    )

    return all_reviews

except Exception as main_error:

    logger.error(
        f"❌ Main scraping failed: {main_error}"
    )

    logger.warning(
        "⚠️ Switching to Serper fallback..."
    )

    return await fetch_from_serper_fallback(
        company_name,
        limit=target_limit
    )
```

# ==========================================================

# REVIEW SERVICE

# ==========================================================

class ReviewService:

```
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

            formatted_reviews = []

            for review in reviews:

                created_at = getattr(
                    review,
                    "google_review_time",
                    None
                )

                if created_at:
                    created_at = created_at.isoformat()

                formatted_reviews.append({

                    "id": getattr(review, "id", None),

                    "author_name": getattr(
                        review,
                        "author_name",
                        "Anonymous"
                    ),

                    "rating": getattr(review, "rating", 0),

                    "text": getattr(review, "text", ""),

                    "review_text": getattr(review, "text", ""),

                    "created_at": created_at,

                    "relative_time_description": created_at,

                    "review_likes": getattr(
                        review,
                        "review_likes",
                        0
                    ),

                    "sentiment": (
                        "positive"
                        if getattr(review, "rating", 0) >= 4
                        else "negative"
                        if getattr(review, "rating", 0) <= 2
                        else "neutral"
                    )
                })

            logger.info(
                f"✅ Loaded {len(formatted_reviews)} reviews from PostgreSQL"
            )

            return formatted_reviews

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

                raise Exception(
                    "Company not found"
                )

            logger.info(
                f"🚀 Starting sync for: {company.name}"
            )

            reviews = await fetch_reviews_from_google(

                place_id=company.google_place_id,

                company_id=company_id,

                session=session,

                target_limit=300
            )

            if not reviews:

                logger.warning(
                    "⚠️ No reviews fetched"
                )

                return {
                    "status": "success",
                    "ingested_count": 0
                }

            ingested_count = 0
            skipped_existing = 0

            for item in reviews:

                try:

                    existing_stmt = select(
                        Review
                    ).where(
                        Review.google_review_id
                        ==
                        item["google_review_id"]
                    )

                    existing_result = await session.execute(
                        existing_stmt
                    )

                    existing_review = (
                        existing_result
                        .scalars()
                        .first()
                    )

                    if existing_review:
                        skipped_existing += 1
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

                except Exception as item_error:

                    logger.error(
                        f"❌ Failed saving review: {item_error}"
                    )

                    continue

            await session.commit()

            logger.info(
                f"✅ PostgreSQL ingest complete: {ingested_count}"
            )

            logger.info(
                f"⚠️ Existing skipped: {skipped_existing}"
            )

            return {
                "status": "success",
                "ingested_count": ingested_count,
                "skipped_existing": skipped_existing
            }

        except Exception as e:

            await session.rollback()

            logger.exception(
                "❌ Ingest failed"
            )

            return {
                "status": "error",
                "ingested_count": 0,
                "message": str(e)
            }
```
