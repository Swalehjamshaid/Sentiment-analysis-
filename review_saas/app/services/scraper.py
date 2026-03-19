import logging
import hashlib
import asyncio
import re
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

def parse_relative_date(date_text: str) -> datetime:
    now = datetime.utcnow()
    date_text = (date_text or "").lower()
    number = 1
    for part in date_text.split():
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
    limit: int = 100,
    **kwargs
) -> List[Dict[str, Any]]:

    reviews: List[Dict[str, Any]] = []
    # 🎯 SOLID LOGIC: Use a direct search URL which is more reliable than googleusercontent
    place_url = f"https://www.google.com/maps/search/?api=1&query=Google&query_place_id={place_id}"

    try:
        async with async_playwright() as p:
            # Emulate an iPhone 13 for a simpler HTML layout
            iphone = p.devices['iPhone 13']
            browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
            context = await browser.new_context(**iphone, locale="en-US")
            
            page = await context.new_page()
            logger.info(f"🚀 Mobile Scraper: Fetching reviews for {place_id}")

            await page.goto(place_url, wait_until="networkidle", timeout=60000)

            # 1. Handle Consent / Cookies (Mobile Style)
            try:
                await page.click('button:has-text("Accept all")', timeout=5000)
            except:
                pass

            # 2. Open Reviews Section
            # On mobile, we look for any element mentioning "Reviews"
            try:
                await page.click('button:has-text("Reviews")', timeout=10000)
                await page.wait_for_timeout(2000)
            except:
                logger.warning("⚠️ Could not find 'Reviews' tab, attempting to find any star rating link...")
                try:
                    await page.click('div[aria-label*="stars"]', timeout=5000)
                except:
                    logger.error("❌ Failed to navigate to reviews panel")
                    await browser.close()
                    return []

            collected_ids = set()
            scroll_attempts = 0
            
            # 3. Scrape Loop
            while len(reviews) < limit and scroll_attempts < 40:
                # Expand "More" buttons
                mores = await page.query_selector_all('text=More')
                for m in mores:
                    try: await m.click(timeout=300)
                    except: pass

                # Use generic selectors that work across both mobile and desktop
                elements = await page.query_selector_all('div[data-review-id], div.jftiEf')

                for r in elements:
                    try:
                        author_el = await r.query_selector('.d4r55, .My579')
                        text_el = await r.query_selector('.wiI7pd')
                        date_el = await r.query_selector('.rsqaWe')
                        rating_el = await r.query_selector('[aria-label*="star"]')

                        author = await author_el.inner_text() if author_el else "Google User"
                        text = await text_el.inner_text() if text_el else ""
                        date_text = await date_el.inner_text() if date_el else ""
                        
                        review_id = hashlib.md5(f"{author}{text}".encode()).hexdigest()
                        if review_id in collected_ids: continue

                        rating_raw = await rating_el.get_attribute("aria-label") if rating_el else "0"
                        match = re.search(r"\d", rating_raw)
                        rating = int(match.group()) if match else 0

                        reviews.append({
                            "review_id": review_id,
                            "rating": rating,
                            "text": text,
                            "author_name": author,
                            "google_review_time": parse_relative_date(date_text).isoformat()
                        })
                        collected_ids.add(review_id)
                        if len(reviews) >= limit: break
                    except:
                        continue

                # Scroll inside the view
                await page.evaluate("window.scrollBy(0, 2000)")
                await page.wait_for_timeout(2000)
                scroll_attempts += 1

            await browser.close()
            logger.info(f"✅ Fetched {len(reviews)} reviews successfully")
            return reviews

    except Exception as e:
        logger.error(f"❌ Scraper Failure: {str(e)}")
        return []
