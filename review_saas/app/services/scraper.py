import logging
import hashlib
import json
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
    # Using the direct search URL which triggers the data-heavy layout
    place_url = f"https://www.google.com/maps/search/?api=1&query=Google&query_place_id={place_id}"

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
            page = await context.new_page()

            # --- THE ADVANCED TECHNIQUE: INTERCEPTING DATA ---
            # We listen for the specific background data Google sends
            async def handle_response(response):
                if "listreviews" in response.url or "preview/review" in response.url:
                    logger.info("📡 Background Review Data Detected!")

            page.on("response", handle_response)

            logger.info(f"🚀 Advanced Intercept Scrape: {place_id}")
            await page.goto(place_url, wait_until="networkidle", timeout=60000)

            # Handle Cookie Consent
            try:
                await page.click('button:has-text("Accept all")', timeout=5000)
                await page.wait_for_timeout(2000)
            except:
                pass

            # Force the review pane to open by clicking the star rating
            try:
                await page.click('button[aria-label*="reviews"]', timeout=10000)
                await page.wait_for_timeout(5000)
            except:
                logger.warning("⚠️ Review trigger not found, attempting auto-scroll.")

            collected_ids = set()
            scroll_attempts = 0
            
            while len(reviews) < limit and scroll_attempts < 40:
                # Targeted scraping of the review cards
                elements = await page.query_selector_all('div.jftiEf')
                
                for r in elements:
                    try:
                        author_el = await r.query_selector('.d4r55')
                        text_el = await r.query_selector('.wiI7pd')
                        date_el = await r.query_selector('.rsqaWe')
                        rating_el = await r.query_selector('span.kvMYJc')

                        author = await author_el.inner_text() if author_el else "User"
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

                # Scroll the review list area
                await page.mouse.move(400, 500)
                await page.mouse.wheel(0, 3000)
                await page.wait_for_timeout(2500)
                scroll_attempts += 1

            await browser.close()
            logger.info(f"✅ Advanced Results: {len(reviews)} reviews.")
            return reviews

    except Exception as e:
        logger.error(f"❌ Advanced Technique Failed: {str(e)}")
        return []
