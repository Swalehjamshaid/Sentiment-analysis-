import logging
import hashlib
import asyncio
import re
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from playwright.async_api import async_playwright, devices

logger = logging.getLogger(__name__)

def parse_relative_date(date_text: str) -> datetime:
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
    limit: int = 100,
    **kwargs
) -> List[Dict[str, Any]]:
    
    reviews: List[Dict[str, Any]] = []
    # Force the mobile reviews URL structure
    place_url = f"https://www.google.com/maps/search/?api=1&query=Google&query_place_id={place_id}"

    try:
        async with async_playwright() as p:
            # Logic: Emulate an iPhone 13 to get the simpler Mobile Layout
            iphone = p.devices['iPhone 13']
            browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
            
            context = await browser.new_context(
                **iphone,
                locale="en-US"
            )
            page = await context.new_page()

            logger.info(f"📱 Emulating Mobile for Place ID: {place_id}")
            await page.goto(place_url, wait_until="commit", timeout=60000)

            # 1. Handle Consent
            try:
                await page.click('button:has-text("Accept all")', timeout=5000)
            except:
                pass

            # 2. Open Reviews (Mobile logic is different)
            try:
                # On mobile, we look for the text "Reviews" or the rating stars
                await page.click('button:has-text("Reviews")', timeout=10000)
                await page.wait_for_timeout(2000)
            except:
                logger.warning("⚠️ Could not find mobile Reviews button, trying scroll...")

            collected_ids = set()
            scroll_attempts = 0
            
            while len(reviews) < limit and scroll_attempts < 40:
                # Expand "More" links
                mores = await page.query_selector_all('text=More')
                for m in mores:
                    try: await m.click(timeout=500)
                    except: pass

                # Mobile Review Selectors are much simpler
                # We look for the common review block class
                elements = await page.query_selector_all('div[data-review-id]')
                if not elements:
                    # Fallback for different mobile layouts
                    elements = await page.query_selector_all('.K77u8b')

                for r in elements:
                    try:
                        # Author, Text, and Rating extraction
                        author_el = await r.query_selector('.al6Kxe .My579') 
                        text_el = await r.query_selector('.wiI7pd')
                        date_el = await r.query_selector('.rsqaWe')
                        
                        # Rating is usually in the aria-label of the stars container
                        rating_el = await r.query_selector('[aria-label*="stars"]')
                        
                        author = await author_el.inner_text() if author_el else "Google User"
                        text = await text_el.inner_text() if text_el else ""
                        date_text = await date_el.inner_text() if date_el else ""
                        
                        review_id = hashlib.md5(f"{author}{text}".encode()).hexdigest()
                        if review_id in collected_ids: continue

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

                # Mobile scrolling is just a standard page swipe
                await page.evaluate("window.scrollBy(0, 2000)")
                await page.wait_for_timeout(2000)
                scroll_attempts += 1

            await browser.close()
            logger.info(f"✅ Mobile Logic Success! Fetched {len(reviews)} reviews.")
            return reviews

    except Exception as e:
        logger.error(f"❌ Scraper Failure: {str(e)}")
        return []
