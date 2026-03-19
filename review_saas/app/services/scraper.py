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
    limit: int = 500,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    retries: int = 3
) -> List[Dict[str, Any]]:

    reviews: List[Dict[str, Any]] = []
    start_dt = datetime.fromisoformat(start_date) if start_date else None
    end_dt = datetime.fromisoformat(end_date) if end_date else None

    # Use the 'lrd' parameter in the URL to try and force the review overlay
    reviews_url = f"https://www.google.com/maps/search/?api=1&query=Google&query_place_id={place_id}"

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
                    viewport={'width': 1280, 'height': 900}
                )
                page = await context.new_page()

                logger.info(f"🚀 Scraping Attempt {attempt} for Place ID: {place_id}")
                await page.goto(reviews_url, wait_until="networkidle", timeout=60000)

                # --- 1. Navigate to the Reviews Section ---
                try:
                    # Search for any button containing "reviews" or the review count
                    review_trigger = page.locator('button:has-text("reviews")').first
                    await review_trigger.click(timeout=10000)
                    await page.wait_for_timeout(3000)
                except Exception:
                    logger.warning("⚠️ Standard review button not found, searching for 'Reviews' tab...")
                    try:
                        await page.click('button[role="tab"]:has-text("Reviews")', timeout=5000)
                    except:
                        # Final fallback: Click the star rating area
                        try:
                            await page.click('span[aria-label*="stars"]', timeout=5000)
                        except:
                            logger.warning("⚠️ All navigation attempts failed. Checking if already on page.")

                # --- 2. Set Sorting to Newest ---
                try:
                    await page.click('button[aria-label="Sort reviews"]', timeout=5000)
                    await page.click('div[role="menuitemradio"]:has-text("Newest")', timeout=5000)
                    await page.wait_for_timeout(2000)
                except:
                    logger.warning("⚠️ Could not sort by Newest.")

                collected_ids = set()
                scroll_attempts = 0
                max_idle_scrolls = 10
                idle_counter = 0

                while len(reviews) < limit:
                    prev_count = len(reviews)

                    # --- 3. Click 'More' to expand long reviews ---
                    more_btns = await page.query_selector_all('button:has-text("More")')
                    for btn in more_btns:
                        try: await btn.click(timeout=500)
                        except: continue

                    # --- 4. Extract Review Data ---
                    # 'jftiEf' is the most consistent container for a Google Review
                    elements = await page.query_selector_all('div.jftiEf')
                    
                    for r in elements:
                        try:
                            # Using specific classes and JS names for better accuracy
                            author_el = await r.query_selector('.d4r55')
                            text_el = await r.query_selector('.wiI7pd')
                            rating_el = await r.query_selector('span.kvMYJc')
                            date_el = await r.query_selector('.rsqaWe')

                            author = await author_el.inner_text() if author_el else "Anonymous"
                            text = await text_el.inner_text() if text_el else ""
                            date_text = await date_el.inner_text() if date_el else ""

                            # Unique ID Generation (MD5)
                            unique_str = f"{author}{text}{date_text}"
                            review_id = hashlib.md5(unique_str.encode()).hexdigest()

                            if review_id in collected_ids:
                                continue

                            rating_raw = await rating_el.get_attribute("aria-label") if rating_el else "0"
                            try:
                                rating = int(re.search(r'\d', rating_raw).group())
                            except:
                                rating = 0

                            review_time = parse_relative_date(date_text)

                            # Apply Date Filters if provided
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

                        except Exception:
                            continue

                    # --- 5. Perform the Scroll ---
                    # We move the mouse to the center and scroll the wheel
                    await page.mouse.move(600, 500)
                    await page.mouse.wheel(0, 4000)
                    await page.wait_for_timeout(2000)

                    # Check if we are still finding new data
                    if len(reviews) == prev_count:
                        idle_counter += 1
                        if idle_counter >= max_idle_scrolls:
                            logger.info("🛑 End of review list reached.")
                            break
                    else:
                        idle_counter = 0

                await browser.close()
                
                if len(reviews) > 0:
                    logger.info(f"✅ Success! Fetched {len(reviews)} reviews for {place_id}")
                    return reviews
                else:
                    logger.warning(f"⚠️ No reviews captured on attempt {attempt}. Retrying...")

        except Exception as e:
            logger.error(f"❌ Scraper failure on attempt {attempt}: {str(e)}")
            await asyncio.sleep(2)

    return reviews
