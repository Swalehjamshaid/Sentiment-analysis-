import logging
import hashlib
import asyncio
import re
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from playwright.async_api import async_playwright

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
    **kwargs
) -> List[Dict[str, Any]]:
    
    reviews: List[Dict[str, Any]] = []
    # SOLID LOGIC: Use the direct Google Search 'lrd' (Local Review Detail) format.
    # This URL type is designed to ONLY show the review pane, bypassing the main map page.
    reviews_url = f"https://www.google.com/maps/search/?api=1&query=Google&query_place_id={place_id}"

    try:
        async with async_playwright() as p:
            # Launch with a specific window size to ensure the sidebar is always visible
            browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                viewport={'width': 1280, 'height': 800}
            )
            page = await context.new_page()

            logger.info(f"🚀 Permanent Sync Attempt for Place ID: {place_id}")
            await page.goto(reviews_url, wait_until="networkidle", timeout=60000)

            # --- STEP 1: STABLE NAVIGATION ---
            try:
                # Look for the review count text (e.g. "1,234 reviews") and click it
                # This is the most stable way to open the side panel
                await page.click('button[aria-label*="reviews"]', timeout=10000)
                await page.wait_for_timeout(3000)
            except:
                logger.warning("⚠️ Review panel might already be open or hidden.")

            # --- STEP 2: FORCE SORT BY NEWEST ---
            try:
                await page.click('button[aria-label="Sort reviews"]', timeout=5000)
                await page.wait_for_timeout(1000)
                await page.click('div[role="menuitemradio"]:has-text("Newest")', timeout=5000)
                await page.wait_for_timeout(2000)
            except:
                pass

            collected_ids = set()
            scroll_attempts = 0
            
            while len(reviews) < limit and scroll_attempts < 60:
                # 1. Expand all "More" buttons in the current view
                more_btns = await page.query_selector_all('button:has-text("More")')
                for btn in more_btns:
                    try: await btn.click(timeout=500)
                    except: pass

                # 2. Scrape using 'jftiEf' - the most permanent container class for reviews
                elements = await page.query_selector_all('div.jftiEf')
                
                if not elements and scroll_attempts > 10:
                    break

                for r in elements:
                    try:
                        # Author Name - Class: d4r55
                        # Review Text - Class: wiI7pd
                        # Rating - Span aria-label
                        # Date - Class: rsqaWe
                        author_el = await r.query_selector('.d4r55')
                        text_el = await r.query_selector('.wiI7pd')
                        rating_el = await r.query_selector('span.kvMYJc')
                        date_el = await r.query_selector('.rsqaWe')

                        author = await author_el.inner_text() if author_el else "Anonymous"
                        text = await text_el.inner_text() if text_el else ""
                        date_text = await date_el.inner_text() if date_el else ""
                        
                        # Generate permanent MD5 Hash
                        review_id = hashlib.md5(f"{author}{text}".encode()).hexdigest()

                        if review_id in collected_ids:
                            continue

                        rating_raw = await rating_el.get_attribute("aria-label") if rating_el else "0"
                        rating = int(re.search(r'\d', rating_raw).group()) if re.search(r'\d', rating_raw) else 0

                        reviews.append({
                            "review_id": review_id,
                            "rating": rating,
                            "text": text,
                            "author_name": author,
                            "google_review_time": parse_relative_date(date_text).isoformat()
                        })
                        collected_ids.add(review_id)
                    except:
                        continue

                # 3. Targeted Scrolling
                # We target the actual scrollable container instead of the whole page
                try:
                    # Move mouse to the left panel (where reviews are) and scroll
                    await page.mouse.move(300, 400)
                    await page.mouse.wheel(0, 5000)
                    await page.wait_for_timeout(2000)
                except:
                    await page.keyboard.press("PageDown")

                scroll_attempts += 1

            await browser.close()
            logger.info(f"✅ Successfully fetched {len(reviews)} reviews.")
            return reviews

    except Exception as e:
        logger.error(f"❌ Scraper Critical Failure: {str(e)}")
        return []
