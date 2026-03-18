# filename: app/services/scraper.py
import asyncio
import logging
from datetime import datetime
from typing import List, Dict, Any
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

async def fetch_reviews(place_id: str, limit: int = 50, skip: int = 0) -> List[Dict[str, Any]]:
    reviews = []
    # Use the Google Maps Search URL for the specific Place ID
    place_url = f"https://www.google.com/maps/search/?api=1&query=Google&query_place_id={place_id}"

    try:
        async with async_playwright() as p:
            # Launch Chromium with args needed for Railway/Docker
            browser = await p.chromium.launch(
                headless=True, 
                args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
            )
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
            page = await context.new_page()

            logger.info(f"🚀 Playwright Browser launching for Place ID: {place_id}")
            await page.goto(place_url, timeout=60000)

            # Wait for the 'Reviews' tab or button to appear and click it
            try:
                review_btn = 'button[jsaction*="pane.reviewChart.moreReviews"]'
                await page.wait_for_selector(review_btn, timeout=15000)
                await page.click(review_btn)
                await page.wait_for_timeout(3000)
            except Exception:
                logger.warning("Could not find 'More Reviews' button, trying to read page directly.")

            # Scroll to load reviews
            for _ in range(5):
                await page.mouse.wheel(0, 4000)
                await page.wait_for_timeout(2000)

            # Extract review elements
            elements = await page.query_selector_all('div.jftiEf')
            
            for r in elements[:limit]:
                try:
                    text_el = await r.query_selector('.wiI7pd')
                    author_el = await r.query_selector('.d4r55')
                    rating_el = await r.query_selector('span.kvMYJc')
                    
                    text = await text_el.inner_text() if text_el else ""
                    author = await author_el.inner_text() if author_el else "Google User"
                    
                    # Get star rating from aria-label (e.g., "5 stars")
                    rating_raw = await rating_el.get_attribute("aria-label") if rating_el else "0"
                    rating = int(rating_raw.split()[0]) if rating_raw and rating_raw[0].isdigit() else 0

                    if text:
                        reviews.append({
                            "review_id": f"pw_{hash(text + author)}",
                            "rating": rating,
                            "text": text,
                            "author_name": author,
                            "google_review_time": datetime.utcnow().isoformat()
                        })
                except Exception:
                    continue
            
            await browser.close()
            logger.info(f"✨ Successfully scraped {len(reviews)} reviews using Playwright.")

    except Exception as e:
        logger.error(f"❌ Playwright Scraper Failed: {str(e)}")
    
    return reviews
