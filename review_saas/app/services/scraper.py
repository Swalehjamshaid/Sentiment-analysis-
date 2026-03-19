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

async def fetch_reviews(place_id: str, limit: int = 150, **kwargs) -> List[Dict[str, Any]]:
    reviews: List[Dict[str, Any]] = []
    # Use the Direct Search URL
    place_url = f"https://www.google.com/maps/search/?api=1&query=Google&query_place_id={place_id}"

    try:
        async with async_playwright() as p:
            # 📱 TECHNIQUE: Emulate an iPhone 13. Mobile pages are 10x easier to scrape!
            iphone = p.devices['iPhone 13']
            browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
            context = await browser.new_context(**iphone, locale="en-US")
            page = await context.new_page()

            logger.info(f"📱 Mobile Ghost Scrape: {place_id}")
            await page.goto(place_url, wait_until="networkidle", timeout=60000)

            # 1. Bypass Consent
            try:
                await page.click('button:has-text("Accept all")', timeout=5000)
            except: pass

            # 2. On Mobile, reviews are often already visible or under a simple "Reviews" text
            try:
                await page.click('text=Reviews', timeout=10000)
                await page.wait_for_timeout(2000)
            except:
                logger.warning("⚠️ Mobile 'Reviews' tab not found, attempting direct scroll.")

            collected_ids = set()
            scroll_attempts = 0
            
            while len(reviews) < limit and scroll_attempts < 40:
                # Targeted Mobile Selectors (Google uses 'data-review-id' globally)
                elements = await page.query_selector_all('[data-review-id]')
                
                for r in elements:
                    try:
                        # Mobile-specific classes (very stable)
                        author_el = await r.query_selector('.My579') 
                        text_el = await r.query_selector('.wiI7pd')
                        rating_el = await r.query_selector('[aria-label*="star"]')
                        date_el = await r.query_selector('.rsqaWe')

                        author = await author_el.inner_text() if author_el else "Guest"
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
                    except: continue

                # Standard Mobile Scroll
                await page.evaluate("window.scrollBy(0, 2000)")
                await asyncio.sleep(2)
                scroll_attempts += 1

            await browser.close()
            logger.info(f"✅ Success: Fetched {len(reviews)} reviews via Mobile Emulation.")
            return reviews
    except Exception as e:
        logger.error(f"❌ Scraper Failed: {str(e)}")
        return []
