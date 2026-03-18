import asyncio
import logging
import re
from datetime import datetime
from typing import List, Dict, Any
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

async def fetch_reviews(place_id: str, limit: int = 200, skip: int = 0) -> List[Dict[str, Any]]:
    reviews = []
    # Direct Google Maps URL for the specific Business
    place_url = f"https://www.google.com/maps/search/?api=1&query=Google&query_place_id={place_id}"

    try:
        async with async_playwright() as p:
            # Launch with specific flags for Railway stability
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox", 
                    "--disable-setuid-sandbox", 
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled"
                ]
            )
            
            # Set a desktop viewport to ensure buttons are visible
            context = await browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
            
            page = await context.new_page()
            logger.info(f"🚀 Playwright starting for Place ID: {place_id}")

            # 1. Navigate and wait for the page to be ready
            await page.goto(place_url, timeout=60000, wait_until="networkidle")

            # 2. Open the Reviews Panel
            try:
                # Try clicking the "Reviews" tab or the review count
                review_selectors = [
                    'button[jsaction*="pane.reviewChart.moreReviews"]',
                    'button:has-text("Reviews")',
                    'div[role="tablist"] >> button:nth-child(2)',
                    '.HHmH1c'
                ]
                
                found_button = False
                for selector in review_selectors:
                    try:
                        btn = page.locator(selector).first
                        if await btn.is_visible(timeout=5000):
                            await btn.click()
                            found_button = True
                            logger.info(f"✅ Clicked Reviews button using: {selector}")
                            break
                    except:
                        continue
                
                if not found_button:
                    logger.warning("⚠️ Standard buttons not found, attempting to find any button with 'Reviews' text.")
                    await page.get_by_role("button", name=re.compile(r"Reviews", re.IGNORECASE)).first.click()
                
                await page.wait_for_timeout(3000)
            except Exception as e:
                logger.warning(f"⚠️ Navigation to reviews failed, attempting direct scroll anyway: {e}")

            # 3. Targeted Internal Scrolling
            # On Google Maps, we must scroll the specific div that contains the reviews
            scrollable_selector = 'div[role="main"] >> div[tabindex="-1"]'
            
            last_count = 0
            for i in range(30):  # 30 loops to ensure we hit 200+
                # This is the "Magic Key": It scrolls the internal div, not the body
                await page.evaluate(f'''
                    const scrollable = document.querySelector('div[role="main"] div[tabindex="-1"]');
                    if (scrollable) {{
                        scrollable.scrollTop = scrollable.scrollHeight;
                    }}
                ''')
                
                await page.wait_for_timeout(2000) # Wait for Google to load the next batch
                
                current_elements = await page.query_selector_all('div.jftiEf')
                current_count = len(current_elements)
                
                logger.info(f"🔄 Scrolling loop {i+1}: Found {current_count} reviews")
                
                if current_count >= limit:
                    break
                
                # If the count hasn't changed in 3 loops, we've hit the end
                if current_count == last_count and i > 5:
                    break
                last_count = current_count

            # 4. Data Extraction
            final_elements = await page.query_selector_all('div.jftiEf')
            logger.info(f"🧐 Processing {len(final_elements)} items...")

            for r in final_elements[:limit]:
                try:
                    # Click "More" for long reviews
                    more_btn = await r.query_selector('button:has-text("More")')
                    if more_btn:
                        await more_btn.click()

                    text_el = await r.query_selector('.wiI7pd')
                    author_el = await r.query_selector('.d4r55')
                    rating_el = await r.query_selector('span.kvMYJc')
                    
                    text = await text_el.inner_text() if text_el else "No comment"
                    author = await author_name_el.inner_text() if (author_el := await r.query_selector('.d4r55')) else "Google User"
                    
                    # Rating extraction
                    rating_raw = await rating_el.get_attribute("aria-label") if rating_el else "0"
                    rating = int(rating_raw.split()[0]) if rating_raw and rating_raw[0].isdigit() else 0

                    reviews.append({
                        "review_id": f"pw_{hash(text + author)}",
                        "rating": rating,
                        "text": text,
                        "author_name": author,
                        "google_review_time": datetime.utcnow().isoformat()
                    })
                except:
                    continue
            
            await browser.close()
            logger.info(f"✨ SUCCESS: Scraped {len(reviews)} reviews.")

    except Exception as e:
        logger.error(f"❌ Scraper Critical Failure: {str(e)}")
    
    return reviews
