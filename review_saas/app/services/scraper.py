import asyncio
import logging
import re
from datetime import datetime
from typing import List, Dict, Any
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

async def fetch_reviews(place_id: str, limit: int = 300, skip: int = 0) -> List[Dict[str, Any]]:
    reviews = []
    # DIRECT URL: This forces Google to bypass the main map and show the business details/reviews
    place_url = f"https://www.google.com/maps/search/?api=1&query=Google&query_place_id={place_id}"

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
            )
            
            context = await browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
            
            page = await context.new_page()
            logger.info(f"🚀 Launching Direct Review View for: {place_id}")

            # 1. Navigate and wait for the "Review" elements to actually exist
            await page.goto(place_url, wait_until="networkidle", timeout=60000)
            
            # 2. Trigger the Review Tab if it's not open
            try:
                # Look for the review count text (e.g., "152 reviews") and click it
                review_trigger = page.locator('button[aria-label*="Reviews"]').first
                await review_trigger.click()
                await page.wait_for_timeout(3000)
                logger.info("✅ Reviews panel triggered")
            except Exception:
                logger.warning("Could not find trigger button, attempting direct scroll on container.")

            # 3. Targeted Internal Scrolling
            # This targets the specific scrollable div used by Google Maps
            scrollable_selector = 'div[role="main"] div[tabindex="-1"]'
            
            # Wait for at least one review to appear before we start scrolling
            try:
                await page.wait_for_selector('div.jftiEf', timeout=10000)
            except:
                logger.warning("Initial reviews not visible, starting emergency scroll.")

            last_count = 0
            for i in range(30):  # Increased loops to hit 300
                await page.evaluate('''
                    const scrollable = document.querySelector('div[role="main"] div[tabindex="-1"]');
                    if (scrollable) {
                        scrollable.scrollTop = scrollable.scrollHeight;
                    }
                ''')
                
                await page.wait_for_timeout(2000)
                
                current_elements = await page.query_selector_all('div.jftiEf')
                current_count = len(current_elements)
                logger.info(f"🔄 Scrolling loop {i+1}: Found {current_count} reviews")
                
                if current_count >= limit:
                    break
                if current_count == last_count and i > 8: # If stuck for 8 loops, stop
                    break
                last_count = current_count

            # 4. Data Extraction (Fixed Variable Names)
            final_elements = await page.query_selector_all('div.jftiEf')
            logger.info(f"🧐 Processing {len(final_elements)} items for database...")

            for r in final_elements[:limit]:
                try:
                    # Expand long reviews
                    more_btn = await r.query_selector('button:has-text("More")')
                    if more_btn: await more_btn.click()

                    text_el = await r.query_selector('.wiI7pd')
                    author_el = await r.query_selector('.d4r55')
                    rating_el = await r.query_selector('span.kvMYJc')
                    
                    text = await text_el.inner_text() if text_el else "No comment"
                    author = await author_el.inner_text() if author_el else "Google User"
                    
                    # Rating extraction
                    rating_raw = await rating_el.get_attribute("aria-label") if rating_el else "0"
                    rating_match = re.search(r'(\d+)', rating_raw)
                    rating = int(rating_match.group(1)) if rating_match else 0

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
            logger.info(f"✨ SUCCESS: Collected {len(reviews)} reviews for Postgres.")

    except Exception as e:
        logger.error(f"❌ Scraper Critical Failure: {str(e)}")
    
    return reviews
