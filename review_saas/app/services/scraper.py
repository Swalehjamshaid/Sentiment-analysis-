# ==========================================================
# FILE: app/services/scraper.py
# GOOGLE MAPS REVIEW SCRAPER
# SELENIUMBASE UC MODE + PLAYWRIGHT HYBRID
# ENTERPRISE STABLE VERSION
# ==========================================================

import os
import re
import gc
import time
import random
import hashlib
import asyncio
import logging
import traceback

from datetime import datetime
from typing import Dict, Any, List

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential
)

from fake_useragent import UserAgent

from sqlalchemy import (
    select,
    func,
    desc
)

from sqlalchemy.ext.asyncio import AsyncSession

from seleniumbase import Driver

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
    "gw.dataimpulse.com:823"
)

PROXY_USERNAME = os.getenv(
    "PROXY_USERNAME"
)

PROXY_PASSWORD = os.getenv(
    "PROXY_PASSWORD"
)

HEADLESS = True

SCROLL_PAUSE_MIN = 2
SCROLL_PAUSE_MAX = 4

MAX_SCROLL_ATTEMPTS = 80
MAX_IDLE_SCROLLS = 10

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

        return int(float(value))

    except Exception:

        return default


def clean_review_text(text):

    text = safe_string(text)

    text = text.replace("\n", " ")
    text = text.replace("\r", " ")
    text = text.replace("\t", " ")

    return " ".join(text.split())


def generate_hash(author, text):

    raw = f"{author}_{text}"

    return hashlib.md5(
        raw.encode("utf-8")
    ).hexdigest()


def normalize_rating(label):

    try:

        match = re.search(
            r"([0-9.]+)",
            str(label)
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


def build_google_maps_search_url(query: str):

    query = query.replace(
        " ",
        "+"
    )

    return (
        f"https://www.google.com/maps/search/{query}"
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

    result = await session.execute(
        stmt
    )

    rows = result.scalars().all()

    mapped = {}

    for row in rows:

        mapped[
            row.google_review_id
        ] = row

    return mapped

# ==========================================================
# NORMALIZE REVIEW
# ==========================================================

def normalize_review(
    item: Dict[str, Any],
    company_id: int
):

    try:

        author_name = safe_string(
            item.get("author_name"),
            "Anonymous"
        )

        review_text = clean_review_text(
            item.get("text")
        )

        if not review_text:
            return None

        rating = safe_int(
            item.get("rating"),
            5
        )

        review_date = datetime.utcnow()

        google_review_id = (

            item.get("review_id")

            or generate_hash(
                author_name,
                review_text
            )
        )

        return {

            "google_review_id":
                google_review_id,

            "author_name":
                author_name,

            "rating":
                rating,

            "text":
                review_text,

            "google_review_time":
                review_date,

            "review_likes":
                0,

            "sentiment_score":
                round(rating / 5, 2)
        }

    except Exception as e:

        logger.exception(
            f"❌ NORMALIZE FAILED: {e}"
        )

        return None

# ==========================================================
# SELENIUMBASE DRIVER
# ==========================================================

def create_driver():

    logger.info(
        "🚀 STARTING SELENIUMBASE DRIVER"
    )

    proxy = None

    if (
        PROXY_SERVER
        and PROXY_USERNAME
        and PROXY_PASSWORD
    ):

        proxy = (

            f"{PROXY_USERNAME}:"
            f"{PROXY_PASSWORD}@"
            f"{PROXY_SERVER}"
        )

    driver = Driver(

        uc=True,

        headless=HEADLESS,

        proxy=proxy,

        agent=UserAgent().random,

        incognito=True,

        disable_gpu=True,

        do_not_track=True,

        undetectable=True,

        chromium_arg=[

            "--disable-dev-shm-usage",

            "--no-sandbox",

            "--disable-blink-features=AutomationControlled",

            "--disable-popup-blocking",

            "--disable-notifications",

            "--disable-infobars",

            "--window-size=1400,900",
        ]
    )

    return driver

# ==========================================================
# CAPTCHA DETECTION
# ==========================================================

def is_captcha_page(driver):

    try:

        url = driver.current_url.lower()

        source = driver.page_source.lower()

        keywords = [

            "captcha",

            "sorry",

            "unusual traffic",

            "not a robot"
        ]

        for keyword in keywords:

            if keyword in url:
                return True

            if keyword in source:
                return True

        return False

    except Exception:
        return False

# ==========================================================
# CLICK REVIEWS TAB
# ==========================================================

def open_reviews_panel(driver):

    logger.info(
        "📦 OPENING REVIEWS PANEL"
    )

    buttons = driver.find_elements(
        "css selector",
        "button"
    )

    for btn in buttons:

        try:

            text = safe_string(
                btn.text
            ).lower()

            aria = safe_string(
                btn.get_attribute(
                    "aria-label"
                )
            ).lower()

            combined = f"{text} {aria}"

            if "review" in combined:

                try:

                    driver.execute_script(
                        "arguments[0].click();",
                        btn
                    )

                except Exception:

                    btn.click()

                logger.info(
                    "✅ REVIEWS BUTTON CLICKED"
                )

                time.sleep(8)

                return True

        except Exception:
            pass

    return False

# ==========================================================
# EXTRACT REVIEWS
# ==========================================================

def extract_reviews(
    driver,
    target_limit=500
):

    logger.info(
        "📦 STARTING REVIEW EXTRACTION"
    )

    reviews = []

    seen_ids = set()

    try:

        scroll_container = driver.find_element(
            "css selector",
            'div[role="feed"]'
        )

    except Exception:

        logger.warning(
            "⚠️ REVIEW FEED NOT FOUND"
        )

        return reviews

    idle_scrolls = 0
    previous_count = 0

    for attempt in range(
        MAX_SCROLL_ATTEMPTS
    ):

        try:

            cards = driver.find_elements(

                "css selector",

                'div[data-review-id], div.jftiEf, div[role="article"]'
            )

            logger.info(
                f"📦 REVIEW CARDS FOUND: {len(cards)}"
            )

            for card in cards:

                try:

                    author = ""

                    rating = 5

                    review_text = ""

                    # ==============================
                    # AUTHOR
                    # ==============================

                    try:

                        author_elem = card.find_element(
                            "css selector",
                            ".d4r55"
                        )

                        author = safe_string(
                            author_elem.text
                        )

                    except Exception:
                        pass

                    # ==============================
                    # REVIEW TEXT
                    # ==============================

                    text_selectors = [

                        ".wiI7pd",

                        ".MyEned",

                        "span[class*='wiI7pd']"
                    ]

                    for selector in text_selectors:

                        try:

                            elem = card.find_element(
                                "css selector",
                                selector
                            )

                            review_text = clean_review_text(
                                elem.text
                            )

                            if review_text:
                                break

                        except Exception:
                            pass

                    if not review_text:
                        continue

                    # ==============================
                    # RATING
                    # ==============================

                    try:

                        rating_elem = card.find_element(

                            "css selector",

                            "span[aria-label*='star']"
                        )

                        rating_label = rating_elem.get_attribute(
                            "aria-label"
                        )

                        rating = normalize_rating(
                            rating_label
                        )

                    except Exception:
                        pass

                    # ==============================
                    # UNIQUE ID
                    # ==============================

                    review_id = generate_hash(
                        author,
                        review_text
                    )

                    if review_id in seen_ids:
                        continue

                    seen_ids.add(
                        review_id
                    )

                    reviews.append({

                        "review_id":
                            review_id,

                        "author_name":
                            author,

                        "rating":
                            rating,

                        "text":
                            review_text
                    })

                except Exception:
                    pass

            logger.info(
                f"✅ TOTAL REVIEWS: {len(reviews)}"
            )

            if len(reviews) >= target_limit:

                logger.info(
                    f"🎯 TARGET LIMIT REACHED: {target_limit}"
                )

                break

            # ==================================
            # SCROLL
            # ==================================

            driver.execute_script(
                """
                arguments[0].scrollBy(
                    0,
                    8000
                );
                """,
                scroll_container
            )

            time.sleep(

                random.uniform(
                    SCROLL_PAUSE_MIN,
                    SCROLL_PAUSE_MAX
                )
            )

            # ==================================
            # EXPAND MORE BUTTONS
            # ==================================

            try:

                more_buttons = driver.find_elements(

                    "css selector",

                    "button.w8nwRe"
                )

                for btn in more_buttons:

                    try:

                        driver.execute_script(
                            "arguments[0].click();",
                            btn
                        )

                    except Exception:
                        pass

            except Exception:
                pass

            current_count = len(
                reviews
            )

            if current_count == previous_count:

                idle_scrolls += 1

            else:

                idle_scrolls = 0

            previous_count = current_count

            if idle_scrolls >= MAX_IDLE_SCROLLS:

                logger.warning(
                    "⚠️ SCROLL IDLE LIMIT REACHED"
                )

                break

        except Exception as e:

            logger.exception(
                f"❌ SCROLL FAILED: {e}"
            )

    gc.collect()

    return reviews

# ==========================================================
# MAIN SCRAPER
# ==========================================================

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(
        multiplier=2,
        min=2,
        max=10
    )
)
async def scrape_google_reviews(
    business_name: str,
    target_limit: int = 500
):

    driver = None

    try:

        driver = create_driver()

        logger.info(
            "🌐 VERIFYING PROXY"
        )

        driver.get(
            "https://api.ipify.org"
        )

        logger.info(
            f"🌐 ACTIVE IP: {driver.page_source}"
        )

        # ======================================
        # SEARCH-BASED NAVIGATION
        # ======================================

        search_url = build_google_maps_search_url(
            business_name
        )

        logger.info(
            f"🌐 SEARCH URL: {search_url}"
        )

        driver.get(
            search_url
        )

        time.sleep(10)

        if is_captcha_page(driver):

            logger.warning(
                "⚠️ CAPTCHA DETECTED"
            )

            return []

        opened = open_reviews_panel(
            driver
        )

        if not opened:

            logger.warning(
                "⚠️ REVIEWS PANEL FAILED"
            )

            return []

        reviews = extract_reviews(

            driver,

            target_limit=target_limit
        )

        logger.info(
            f"✅ SCRAPED REVIEWS: {len(reviews)}"
        )

        return reviews

    except Exception as e:

        logger.exception(
            f"❌ SCRAPER FAILED: {e}"
        )

        logger.error(
            traceback.format_exc()
        )

        return []

    finally:

        try:

            if driver:

                driver.quit()

        except Exception:
            pass

# ==========================================================
# FETCH REVIEWS
# ==========================================================

async def fetch_reviews_from_google(

    business_name: str,

    company_id: int,

    session: AsyncSession,

    target_limit: int = 500
):

    logger.info(
        f"🚀 FETCH REVIEWS STARTED | company={company_id}"
    )

    try:

        reviews = await scrape_google_reviews(

            business_name=business_name,

            target_limit=target_limit
        )

        if not reviews:

            logger.warning(
                "⚠️ NO REVIEWS SCRAPED"
            )

            return []

        existing_reviews = await get_existing_reviews(

            session=session,

            company_id=company_id
        )

        inserted_reviews = []

        for idx, item in enumerate(reviews):

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

                if google_review_id in existing_reviews:
                    continue

                review = Review(

                    company_id=
                        company_id,

                    google_review_id=
                        normalized[
                            "google_review_id"
                        ],

                    author_name=
                        normalized[
                            "author_name"
                        ],

                    rating=
                        normalized[
                            "rating"
                        ],

                    text=
                        normalized[
                            "text"
                        ],

                    google_review_time=
                        normalized[
                            "google_review_time"
                        ],

                    review_likes=
                        normalized[
                            "review_likes"
                        ],

                    sentiment_score=
                        normalized[
                            "sentiment_score"
                        ]
                )

                session.add(review)

                inserted_reviews.append({

                    "google_review_id":
                        normalized[
                            "google_review_id"
                        ],

                    "author_name":
                        normalized[
                            "author_name"
                        ],

                    "rating":
                        normalized[
                            "rating"
                        ],

                    "text":
                        normalized[
                            "text"
                        ]
                })

                # ==============================
                # BATCH COMMIT
                # ==============================

                if idx % 50 == 0:

                    await session.commit()

            except Exception as e:

                logger.exception(
                    f"❌ SAVE REVIEW FAILED: {e}"
                )

        try:

            await session.commit()

        except Exception as e:

            logger.exception(
                f"❌ FINAL COMMIT FAILED: {e}"
            )

            await session.rollback()

            return []

        logger.info(
            f"✅ INSERTED REVIEWS: {len(inserted_reviews)}"
        )

        return inserted_reviews

    except Exception as e:

        logger.exception(
            f"❌ FETCH FAILED: {e}"
        )

        try:
            await session.rollback()
        except Exception:
            pass

        return []

# ==========================================================
# ANALYTICS
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

        result = await db.execute(
            stmt
        )

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

        result = await db.execute(
            stmt
        )

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

        result = await db.execute(
            stmt
        )

        avg = result.scalar()

        if avg is None:
            return 0

        return round(
            float(avg),
            2
        )
