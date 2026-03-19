# review_saas/app/services/scraper.py
import logging
import hashlib
import asyncio
import re
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

logger = logging.getLogger(__name__)

def parse_relative_date(date_text: str) -> datetime:
    """Convert Google relative date strings (e.g., '2 months ago') to datetime."""
    now = datetime.utcnow()
    date_text = date_text.lower()

    number = 1
    parts = date_text.split()
    for part in parts:
        if part.isdigit():
            number = int(part)
            break

    if "hour" in date_text: return now - timedelta(hours=number)
    if "day" in date_text: return now - timedelta(days=number)
    if "week" in date_text: return now - timedelta(weeks=number)
    if "month" in date_text: return now - timedelta(days=number * 30)
    if "year" in date_text: return now - timedelta(days=number * 365)
    return now

async def fetch_reviews(
    place_id: str,
    limit: int = 5000,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    retries: int = 3
) -> List[Dict[str, Any]]:

    reviews: List[Dict[str, Any]] = []
    start_dt = datetime.fromisoformat(start_date) if start_date else None
    end_dt = datetime.fromisoformat(end_date) if end_date else None

    # Direct Google Maps URL
    reviews_url = f"https://www.google.com/maps/place/?q=place_id:{place_id}&hl=en"

    attempt = 0
    while attempt < retries:
        attempt += 1
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
                )
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                    viewport={'width': 1920, 'height': 1080}
                )
                page = await context.new_page()

                logger.info(f"🚀 Navigating to Place ID: {place_id} (Attempt {attempt})")
                await page.goto(reviews_url, wait_until="domcontentloaded", timeout=60000)
                await page.wait_for_timeout(5000)

                # Try to click "All Reviews" dynamically
                try:
                    reviews_button = await page.wait_for_selector(
                        "button[jsaction*='reviews']",
                        timeout=10000
                    )
                    await reviews_button.click()
                    await page.wait_for_timeout(3000)
                except PlaywrightTimeoutError:
                    logger.warning("⚠️ 'Reviews' button not found, trying fallback...")

                collected_ids = set()
                scroll_attempts = 0
                max_idle_scrolls = 10

                while len(reviews) < limit and scroll_attempts < 1000:
                    prev_count = len(reviews)

                    # Expand "See more" buttons for long reviews
                    try:
                        more_buttons = await page.query_selector_all('button[jsaction*="expandReview"]')
                        for btn in more_buttons:
                            try:
                                await btn.click(timeout=500)
                            except:
                                continue
                    except:
                        pass

                    # Fetch reviews dynamically
                    try:
                        elements = await page.query_selector_all('div[data-review-id]')
                        for r in elements:
                            try:
                                text_el = await r.query_selector('span[jsname="bN97Pc"]')
                                rating_el = await r.query_selector('span[role="img"]')
                                author_el = await r.query_selector('div[class*="d4r55"]')
                                date_el = await r.query_selector('span[class*="rsqaWe"]')

                                text = await text_el.inner_text() if text_el else ""
                                author = await author_el.inner_text() if author_el else "Anonymous"
                                date_text = await date_el.inner_text() if date_el else ""

                                # Unique ID
                                unique_str = f"{author}{text}{date_text}"
                                review_id = hashlib.md5(unique_str.encode()).hexdigest()
                                if review_id in collected_ids:
                                    continue

                                rating_raw = await rating_el.get_attribute("aria-label") if rating_el else "0"
                                try:
                                    rating = int(next(s for s in rating_raw.split() if s.isdigit()))
                                except:
                                    rating = 0

                                review_time = parse_relative_date(date_text)

                                # Date filtering
                                if start_dt and review_time < start_dt: continue
                                if end_dt and review_time > end_dt: continue

                                if text or rating > 0:
                                    reviews.append({
                                        "review_id": review_id,
                                        "rating": rating,
                                        "text": text,
                                        "author_name": author,
                                        "google_review_time": review_time.isoformat()
                                    })
                                    collected_ids.add(review_id)

                                if len(reviews) >= limit: break

                            except:
                                continue
                    except:
                        pass

                    # Scroll reviews container
                    try:
                        await page.mouse.move(1000, 500)
                        await page.mouse.wheel(0, 4000)
                    except:
                        await page.keyboard.press("PageDown")

                    await page.wait_for_timeout(2500)

                    if len(reviews) == prev_count:
                        scroll_attempts += 1
                        if scroll_attempts >= max_idle_scrolls:
                            break
                    else:
                        scroll_attempts = 0

                await browser.close()
                logger.info(f"✅ Total reviews fetched: {len(reviews)}")

                if len(reviews) > 0:
                    break
                else:
                    logger.warning(f"⚠️ No reviews found on attempt {attempt}, retrying...")

        except Exception as e:
            logger.error(f"❌ Scraper Failure on attempt {attempt}: {str(e)}")
            await asyncio.sleep(2)

    return reviews
