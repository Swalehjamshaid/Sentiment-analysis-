# filename: app/services/scraper.py

import asyncio
import logging
import os
from datetime import datetime
from typing import List, Dict, Any
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

async def fetch_reviews(place_id: str, limit: int = 50, skip: int = 0) -> List[Dict[str, Any]]:
    """
    Scrapes reviews using a real headless browser.
    Bypasses 400/404 errors by acting like a human user.
    """
    reviews = []
    
    # 1. Convert Place ID into a clickable Google Maps URL
    # Google uses this redirect structure to open the specific business pane
    place_url = f"https://www.google.com/maps/search/?api=1&query=Google&query_place_id={place_id}"

    try:
        async with async_playwright() as p:
            # CRITICAL: Launch arguments for Railway/Docker environments
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
            )
            
            # Use a modern User-Agent to look like a real browser
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
            page = await context.new_page()

            logger.info(f"🚀 Playwright navigating to: {place_url}")
            await page.goto(place_url, timeout=60000)

            # 2. Click the "Reviews" button
            # We use a broad selector to catch the 'More reviews' or 'Reviews' tab
            try:
                review_btn_selector = 'button[jsaction*="pane.reviewChart.moreReviews"]'
                await page.wait_for_selector(review_btn_selector, timeout=15000)
                await page.click(review_btn_selector)
                logger.info("✅ Clicked 'More Reviews' button.")
            except Exception as btn_err:
                logger.warning(f"Could not find 'More Reviews' button, checking if already on review page: {btn_err}")

            # Wait for reviews to load
            await page.wait_for_timeout(3000)

            # 3. Scroll to load reviews
            # We scroll 15 times to ensure we hit the 'limit' requested
            logger.info("🖱️ Scrolling to load more reviews...")
            for i in range(15):
                # We scroll inside the review list pane
                await page.mouse.wheel(0, 5000)
                await page.wait_for_timeout(1500)

            # 4. Extract Review Elements
            review_elements = await page.query_selector_all('div.jftiEf')
            logger.info(f"📄 Found {len(review_elements)} review elements on page.")

            for r in review_elements[:limit]:
                try:
                    text_el = await r.query_selector('.wiI7pd')
                    rating_el = await r.query_selector('span.kvMYJc')
                    author_el = await r.query_selector('.d4r55')

                    text = await text_el.inner_text() if text_el else ""
                    rating_raw = await rating_el.get_attribute("aria-label") if rating_el else "0"
                    author = await author_el.inner_text() if author_el else "Google User"

                    # Convert "5 stars" or "4/5" string to integer
                    try:
                        rating = int(rating_raw.split(" ")[0])
                    except:
                        rating = 0

                    if text:  # Only add if there is actual review text
                        reviews.append({
                            # Generate a unique ID based on author and text hash
                            "review_id": f"pw_{hash(text + author)}",
                            "rating": rating,
                            "text": text,
                            "author_name": author,
                            "google_review_time": datetime.utcnow().isoformat()
                        })

                except Exception as e:
                    continue

            await browser.close()
            logger.info(f"✨ Successfully scraped {len(reviews)} reviews.")

    except Exception as e:
        logger.error(f"❌ Playwright Scraper Failed: {e}")

    return reviews
