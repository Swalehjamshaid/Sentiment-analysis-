import logging
import hashlib
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

def parse_relative_date(date_text: str) -> datetime:
    """Approximates a datetime from Google's relative strings (e.g., '2 months ago')."""
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
    limit: int = 300,
    skip: int = 0,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
) -> List[Dict[str, Any]]:
    
    reviews: List[Dict[str, Any]] = []
    start_dt = datetime.fromisoformat(start_date) if start_date else None
    end_dt = datetime.fromisoformat(end_date) if end_date else None

    # Official Google Maps URL for Place IDs
    place_url = f"https://www.google.com/maps/search/?api=1&query=Google&query_place_id={place_id}"

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

            logger.info(f"🚀 Navigating to Place ID: {place_id}")
            await page.goto(place_url, wait_until="networkidle", timeout=60000)

            # 1. Click the 'Reviews' Tab
            try:
                # This locator finds the specific button labeled 'Reviews'
                reviews_btn = page.get_by_role("button", name=re.compile(r"Reviews", re.IGNORECASE))
                await reviews_btn.first.click(timeout=10000)
                await page.wait_for_timeout(3000)
            except Exception:
                logger.warning("⚠️ Could not find explicit 'Reviews' button, trying fallback...")

            # 2. Sort by Newest (Crucial for fresh data)
            try:
                await page.get_by_label("Sort reviews").click(timeout=5000)
                await page.get_by_role("menuitemradio", name="Newest").click()
                await page.wait_for_timeout(2000)
            except Exception:
                logger.warning("⚠️ Could not sort by newest.")

            collected_ids = set()
            scroll_attempts = 0
            MAX_SCROLL = 50 

            # Identify the scrollable container for reviews
            # Google uses a specific div for the list
            scrollable_div = "div.m67qec" 

            while len(reviews) < limit and scroll_attempts < MAX_SCROLL:
                # Expand 'More' buttons for long reviews
                more_btns = await page.query_selector_all('button[aria-label="See more"]')
                for btn in more_btns:
                    try:
                        await btn.click(timeout=500)
                    except:
                        continue

                # Get all review cards
                elements = await page.query_selector_all('div.jftiEf')

                for r in elements:
                    try:
                        text_el = await r.query_selector('.wiI7pd')
                        rating_el = await r.query_selector('span.kvMYJc')
                        author_el = await r.query_selector('.d4r55')
                        date_el = await r.query_selector('.rsqaWe')

                        text = await text_el.inner_text() if text_el else ""
                        author = await author_el.inner_text() if author_el else "Anonymous"
                        date_text = await date_el.inner_text() if date_el else ""
                        
                        # Use MD5 for a permanent unique ID
                        unique_str = f"{author}{text}{date_text}"
                        review_id = hashlib.md5(unique_str.encode()).hexdigest()

                        if review_id in collected_ids:
                            continue

                        rating_raw = await rating_el.get_attribute("aria-label") if rating_el else "0"
                        try:
                            # Extract number from "5 stars"
                            rating = int(next(s for s in rating_raw.split() if s.isdigit()))
                        except:
                            rating = 0

                        review_time = parse_relative_date(date_text)

                        # Filtering
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

                # Scroll inside the reviews container specifically
                try:
                    # We scroll the element that has the scrollbar
                    await page.mouse.move(1000, 500) # Move mouse to center
                    await page.mouse.wheel(0, 4000)
                except:
                    # Fallback scroll
                    await page.keyboard.press("PageDown")

                await page.wait_for_timeout(2000)
                scroll_attempts += 1

                # If no new elements were found, we might be at the end
                if len(elements) == 0 and scroll_attempts > 5:
                    break

            await browser.close()
            logger.info(f"✅ Total reviews successfully fetched: {len(reviews)}")

    except Exception as e:
        logger.error(f"❌ Critical Scraper Failure: {str(e)}")

    return reviews
