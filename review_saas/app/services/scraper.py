# filename: app/services/scraper.py
import asyncio
import logging
import re
from datetime import datetime
from typing import List, Dict, Any
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

async def fetch_reviews(place_id: str, limit: int = 200, skip: int = 0) -> List[Dict[str, Any]]:
    reviews = []
    # Using the direct Google Maps URL for the Place ID
    place_url = f"https://www.google.com/maps/search/?api=1&query=Google&query_place_id={place_id}"

    try:
        async with async_playwright() as p:
            # Added more flags to make the browser "stealthy" and stable on Railway
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox", 
                    "--disable-setuid-sandbox", 
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled"
                ]
            )
            
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
            
            page = await context.new_page()
            logger.info(f"🚀 Playwright starting for: {place_id}")

            # 1. Navigate and wait for content
            await page.goto(place_url, timeout=60000, wait_until="networkidle")

            # 2. Find and Click the 'Reviews' tab/button
            # We use a more generic search for the word 'Reviews' to fix your 'Button not found' error
            try:
                # Wait for any text that says "Reviews" (case-insensitive)
                review_btn = page.get_by_role("button", name=re.compile(r"Reviews", re.IGNORECASE)).first
                await review_btn.wait_for(timeout=10000)
                await review_btn.click()
                logger.info("✅ Clicked Reviews button")
                await page.wait_for_timeout(3000)
            except Exception as e:
                logger.warning(f"⚠️ Standard button not found ({e}), attempting direct scroll.")

            # 3. Dynamic Scrolling to get 200+ reviews
            # We target the specific scrollable container in Google Maps
            scrollable_div = 'div[role="main"] >> div[role="region"] >> div[tabindex="-1"]'
            
            last_count = 0
            for i in range(25):  # Increased iterations to reach 200 reviews
                await page.mouse.wheel(0, 8000)
                await page.wait_for_timeout(1500)
                
                # Check how many we have found so far
                current_elements = await page.query_selector_all('div.jftiEf')
                if len(current_elements) >= limit:
                    break
                
                if len(current_elements) == last_count and i > 10:
                    logger.info("Reached end of list or page slow to load.")
                    break
                last_count = len(current_elements)
                logger.info(f"Scrolling... Found {last_count} elements")

            # 4. Data Extraction
            elements = await page.query_selector_all('div.jftiEf')
            logger.info(f"🧐 Processing {len(elements)} items...")

            for r in elements[:limit]:
                try:
                    # Click "More" on long reviews if it exists
                    more_btn = await r.query_selector('button:has-text("More")')
                    if more_btn:
                        await more_btn.click()
                        await page.wait_for_timeout(200)

                    text_el = await r.query_selector('.wiI7pd')
                    author_el = await r.query_selector('.d4r55')
                    rating_el = await r.query_selector('span.kvMYJc')
                    
                    text = await text_el.inner_text() if text_el else "No Comment"
                    author = await author_el.inner_text() if author_el else "Google User"
                    
                    # Extract numeric rating from aria-label
                    rating_raw = await rating_el.get_attribute("aria-label") if rating_el else "0"
                    rating = int(rating_raw.split()[0]) if rating_raw and rating_raw[0].isdigit() else 0

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
            logger.info(f"✨ MISSION COMPLETE: Scraped {len(reviews)} reviews.")

    except Exception as e:
        logger.error(f"❌ Scraper Failed: {str(e)}")
    
    return reviews
