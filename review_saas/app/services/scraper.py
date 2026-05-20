# ==========================================================
# FILE: app/services/scraper.py
# PROFESSIONAL GOOGLE REVIEWS SCRAPER
# SELENIUMBASE + RESIDENTIAL PROXY + UC MODE
# ==========================================================

import os
import gc
import re
import time
import random
import hashlib
import logging
import traceback

from datetime import datetime
from typing import Dict, Any, List

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

from seleniumbase import Driver

from selenium.webdriver.common.by import By

from selenium.webdriver.common.keys import Keys

from selenium.webdriver.support.ui import WebDriverWait

from selenium.webdriver.support import expected_conditions as EC

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
# ENVIRONMENT VARIABLES
# ==========================================================

PROXY_SERVER = os.getenv(
    "PROXY_SERVER"
)

PROXY_USERNAME = os.getenv(
    "PROXY_USERNAME"
)

PROXY_PASSWORD = os.getenv(
    "PROXY_PASSWORD"
)

# ==========================================================
# CONFIG
# ==========================================================

HEADLESS = False

MAX_SCROLL_ATTEMPTS = 150

MAX_IDLE_SCROLLS = 15

SCROLL_PAUSE_MIN = 2

SCROLL_PAUSE_MAX = 4

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

    text = " ".join(text.split())

    return text[:5000]


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


def generate_hash(author, text):

    raw = f"{author}_{text}"

    return hashlib.md5(
        raw.encode("utf-8")
    ).hexdigest()


def build_google_maps_search_url(query):

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
                datetime.utcnow(),

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
# CREATE DRIVER
# ==========================================================

def create_driver():

    logger.info(
        "🚀 STARTING SELENIUMBASE UC DRIVER"
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

        undetectable=True,

        incognito=True,

        guest_mode=True,

        do_not_track=True,

        headless=HEADLESS,

        disable_gpu=True,

        proxy=proxy,

        agent=UserAgent().random,

        chromium_arg=[

            "--disable-dev-shm-usage",

            "--no-sandbox",

            "--disable-blink-features=AutomationControlled",

            "--disable-popup-blocking",

            "--disable-notifications",

            "--disable-infobars",

            "--window-size=1440,960",

            "--lang=en-US",
        ]
    )

    return driver

# ==========================================================
# CAPTCHA DETECTION
# ==========================================================

def is_rate_limited(driver):

    try:

        current_url = safe_string(
            driver.current_url
        ).lower()

        source = safe_string(
            driver.page_source
        ).lower()

        keywords = [

            "captcha",

            "recaptcha",

            "unusual traffic",

            "not a robot",

            "/sorry/"
        ]

        for keyword in keywords:

            if keyword in current_url:
                return True

            if keyword in source:
                return True

        return False

    except Exception:
        return False

# ==========================================================
# WARMUP SESSION
# ==========================================================

def warmup_session(driver):

    try:

        logger.info(
            "🔥 WARMING SESSION"
        )

        driver.get(
            "https://www.google.com"
        )

        time.sleep(8)

        driver.execute_script(
            "window.scrollBy(0, 400);"
        )

        time.sleep(3)

        driver.execute_script(
            "window.scrollBy(0, -200);"
        )

        time.sleep(3)

    except Exception as e:

        logger.exception(
            f"❌ WARMUP FAILED: {e}"
        )

# ==========================================================
# CLICK SEARCH RESULT
# ==========================================================

def click_first_search_result(driver):

    logger.info(
        "📦 CLICKING SEARCH RESULT"
    )

    selectors = [

        'a.hfpxzc',

        'div[role="article"] a',

        'a[jsaction]',

        'a[href*="/maps/place/"]',

        'div.Nv2PK a',

        'div.Nv2PK',

        'a[data-cid]',

        'a[data-value]'
    ]

    for selector in selectors:

        try:

            results = driver.find_elements(
                "css selector",
                selector
            )

            logger.info(
                f"📦 RESULTS FOUND ({selector}): {len(results)}"
            )

            if not results:
                continue

            first = results[0]

            try:

                driver.execute_script(
                    """
                    arguments[0].scrollIntoView({
                        behavior: 'smooth',
                        block: 'center'
                    });
                    """,
                    first
                )

                time.sleep(2)

            except Exception:
                pass

            click_methods = [

                lambda: driver.execute_script(
                    "arguments[0].click();",
                    first
                ),

                lambda: first.click(),

                lambda: first.send_keys(Keys.ENTER)
            ]

            for method in click_methods:

                try:

                    method()

                    logger.info(
                        "✅ SEARCH RESULT CLICKED"
                    )

                    time.sleep(12)

                    return True

                except Exception:
                    continue

        except Exception as e:

            logger.exception(
                f"❌ SEARCH CLICK FAILED: {e}"
            )

    return False

# ==========================================================
# OPEN REVIEWS PANEL
# ==========================================================

def open_reviews_panel(driver):

    logger.info(
        "📦 OPENING REVIEWS PANEL"
    )

    time.sleep(15)

    smart_selectors = [

        "button[aria-label*='Reviews']",

        "button[aria-label*='reviews']",

        "button[data-value='Reviews']",

        "div[role='tab']",

        "button[jsaction]",

        "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'review')]",

        "//div[contains(@role,'tab')]//*[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'review')]",

        "//span[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'review')]"
    ]

    try:

        # ==================================================
        # SMART SELECTOR PHASE
        # ==================================================

        for selector in smart_selectors:

            try:

                logger.info(
                    f"🔍 TRYING SELECTOR: {selector}"
                )

                if selector.startswith("//"):

                    elements = driver.find_elements(
                        By.XPATH,
                        selector
                    )

                else:

                    elements = driver.find_elements(
                        By.CSS_SELECTOR,
                        selector
                    )

                logger.info(
                    f"📦 FOUND ELEMENTS: {len(elements)}"
                )

                for element in elements:

                    try:

                        text = safe_string(
                            element.text
                        ).lower()

                        aria = safe_string(
                            element.get_attribute(
                                "aria-label"
                            )
                        ).lower()

                        combined = (
                            f"{text} {aria}"
                        ).lower()

                        logger.info(
                            f"🔍 REVIEW ELEMENT: {combined[:120]}"
                        )

                        if (
                            "review" not in combined
                            and "rating" not in combined
                        ):
                            continue

                        driver.execute_script(
                            """
                            arguments[0].scrollIntoView({
                                behavior: 'smooth',
                                block: 'center'
                            });
                            """,
                            element
                        )

                        time.sleep(2)

                        click_methods = [

                            lambda: driver.execute_script(
                                "arguments[0].click();",
                                element
                            ),

                            lambda: element.click(),

                            lambda: element.send_keys(Keys.ENTER)
                        ]

                        for method in click_methods:

                            try:

                                method()

                                logger.info(
                                    "✅ REVIEW BUTTON CLICKED"
                                )

                                time.sleep(10)

                                feed = driver.find_elements(

                                    By.CSS_SELECTOR,

                                    'div[role="feed"]'
                                )

                                if feed:

                                    logger.info(
                                        "✅ REVIEW FEED VERIFIED"
                                    )

                                    return True

                            except Exception:
                                continue

                    except Exception:
                        continue

            except Exception:
                continue

        # ==================================================
        # FALLBACK DOM SCAN
        # ==================================================

        logger.warning(
            "⚠️ SMART SELECTORS FAILED - USING FALLBACK"
        )

        elements = driver.find_elements(

            By.CSS_SELECTOR,

            "button, div, span, a"
        )

        logger.info(
            f"📦 TOTAL CLICKABLE ELEMENTS: {len(elements)}"
        )

        for idx, element in enumerate(elements):

            try:

                text = safe_string(
                    element.text
                ).lower()

                aria = safe_string(
                    element.get_attribute(
                        "aria-label"
                    )
                ).lower()

                title = safe_string(
                    element.get_attribute(
                        "title"
                    )
                ).lower()

                combined = (
                    f"{text} {aria} {title}"
                ).lower()

                if not combined.strip():
                    continue

                logger.info(
                    f"🔍 ELEMENT [{idx}]: {combined[:100]}"
                )

                if (
                    "review" in combined
                    or "reviews" in combined
                    or "rating" in combined
                ):

                    logger.info(
                        f"✅ REVIEW ELEMENT FOUND: {combined}"
                    )

                    driver.execute_script(
                        """
                        arguments[0].scrollIntoView({
                            behavior: 'smooth',
                            block: 'center'
                        });
                        """,
                        element
                    )

                    time.sleep(2)

                    click_methods = [

                        lambda: driver.execute_script(
                            "arguments[0].click();",
                            element
                        ),

                        lambda: element.click(),

                        lambda: element.send_keys(Keys.ENTER)
                    ]

                    for method in click_methods:

                        try:

                            method()

                            logger.info(
                                "✅ REVIEW BUTTON CLICKED"
                            )

                            time.sleep(10)

                            feed = driver.find_elements(

                                By.CSS_SELECTOR,

                                'div[role="feed"]'
                            )

                            if feed:

                                logger.info(
                                    "✅ REVIEW FEED VERIFIED"
                                )

                                return True

                        except Exception:
                            continue

            except Exception:
                continue

    except Exception as e:

        logger.exception(
            f"❌ REVIEW PANEL ERROR: {e}"
        )

    logger.warning(
        "⚠️ REVIEWS BUTTON NOT FOUND"
    )

    return False

# ==========================================================
# EXPAND REVIEW BUTTONS
# ==========================================================

def expand_review_buttons(driver):

    selectors = [

        "button.w8nwRe",

        "button[jsaction*='pane.review.expandReview']"
    ]

    for selector in selectors:

        try:

            buttons = driver.find_elements(
                By.CSS_SELECTOR,
                selector
            )

            for btn in buttons:

                try:

                    driver.execute_script(
                        "arguments[0].click();",
                        btn
                    )

                except Exception:
                    pass

        except Exception:
            pass

# ==========================================================
# EXTRACT REVIEWS
# ==========================================================

def extract_reviews(driver, target_limit=500):

    logger.info(
        "📦 STARTING REVIEW EXTRACTION"
    )

    reviews = []

    seen_ids = set()

    try:

        scroll_container = driver.find_element(

            By.CSS_SELECTOR,

            'div[role="feed"]'
        )

    except Exception as e:

        logger.exception(
            f"❌ REVIEW FEED NOT FOUND: {e}"
        )

        return reviews

    idle_scrolls = 0

    previous_count = 0

    for attempt in range(
        MAX_SCROLL_ATTEMPTS
    ):

        try:

            logger.info(
                f"📦 SCROLL ATTEMPT: {attempt}"
            )

            cards = driver.find_elements(

                By.CSS_SELECTOR,

                'div[data-review-id], div.jftiEf, div[role="article"]'
            )

            logger.info(
                f"📦 REVIEW CARDS FOUND: {len(cards)}"
            )

            for card in cards:

                try:

                    author = ""
                    review_text = ""
                    rating = 5

                    author_selectors = [

                        ".d4r55",

                        ".TSUbDb",

                        "span[class*='d4r55']"
                    ]

                    for selector in author_selectors:

                        try:

                            author_elem = card.find_element(
                                By.CSS_SELECTOR,
                                selector
                            )

                            author = safe_string(
                                author_elem.text
                            )

                            if author:
                                break

                        except Exception:
                            pass

                    text_selectors = [

                        ".wiI7pd",

                        ".MyEned",

                        "span[class*='wiI7pd']",

                        "span[jscontroller]"
                    ]

                    for selector in text_selectors:

                        try:

                            text_elem = card.find_element(
                                By.CSS_SELECTOR,
                                selector
                            )

                            review_text = clean_review_text(
                                text_elem.text
                            )

                            if review_text:
                                break

                        except Exception:
                            pass

                    if not review_text:
                        continue

                    rating_selectors = [

                        "span[aria-label*='star']",

                        "span.kvMYJc"
                    ]

                    for selector in rating_selectors:

                        try:

                            rating_elem = card.find_element(
                                By.CSS_SELECTOR,
                                selector
                            )

                            rating_label = rating_elem.get_attribute(
                                "aria-label"
                            )

                            rating = normalize_rating(
                                rating_label
                            )

                            break

                        except Exception:
                            pass

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
                    continue

            logger.info(
                f"✅ TOTAL REVIEWS: {len(reviews)}"
            )

            if len(reviews) >= target_limit:

                logger.info(
                    f"🎯 TARGET LIMIT REACHED: {target_limit}"
                )

                break

            expand_review_buttons(
                driver
            )

            driver.execute_script(
                """
                arguments[0].scrollBy(
                    0,
                    2800
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
        max=15
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
            "https://ipinfo.io/json"
        )

        logger.info(
            f"🌐 PROXY INFO: {driver.page_source[:500]}"
        )

        warmup_session(
            driver
        )

        search_url = build_google_maps_search_url(
            business_name
        )

        logger.info(
            f"🌐 SEARCH URL: {search_url}"
        )

        driver.get(
            search_url
        )

        time.sleep(12)

        logger.info(
            f"🌐 CURRENT URL: {driver.current_url}"
        )

        logger.info(
            f"🌐 PAGE TITLE: {driver.title}"
        )

        if is_rate_limited(driver):

            logger.warning(
                "⚠️ GOOGLE RATE LIMITED"
            )

            time.sleep(60)

            return []

        clicked = click_first_search_result(
            driver
        )

        if not clicked:

            logger.warning(
                "⚠️ SEARCH RESULT CLICK FAILED"
            )

            return []

        logger.info(
            f"🌐 PAGE TITLE AFTER CLICK: {driver.title}"
        )

        time.sleep(15)

        driver.execute_script(
            "window.scrollBy(0, 500);"
        )

        time.sleep(5)

        opened = open_reviews_panel(
            driver
        )

        if not opened:

            logger.warning(
                "⚠️ REVIEWS PANEL FAILED"
            )

            with open(
                "/tmp/google_debug.html",
                "w",
                encoding="utf-8"
            ) as f:

                f.write(
                    driver.page_source
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

                if idx % 50 == 0:

                    await session.commit()

            except Exception as row_error:

                logger.exception(
                    f"❌ SAVE REVIEW FAILED: {row_error}"
                )

        try:

            await session.commit()

        except Exception as commit_error:

            logger.exception(
                f"❌ FINAL DB COMMIT FAILED: {commit_error}"
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

        logger.error(
            traceback.format_exc()
        )

        try:
            await session.rollback()
        except Exception:
            pass

        return []

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
