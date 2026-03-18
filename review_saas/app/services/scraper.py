import asyncio
import logging
import re
from datetime import datetime
from typing import List, Dict, Any
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

async def fetch_reviews(place_id: str, limit: int = 200, skip: int = 0) -> List[Dict[str, Any]]:
    reviews = []
    # Force the direct Google Maps URL
    place_url = f"https://www.google.com/maps/place/?q=place_id:{place_id}"

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
            
            # Use a Desktop viewport to ensure the Reviews button is visible
            context = await browser.new_context(
                viewport={'width': 1280, 'height': 800},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
            
            page = await context.new_page()
            logger.info(f"🚀 Playwright starting for Place ID: {place_id}")

            # 1. Navigate and wait for the page to be ready
            await page.goto(place_url, timeout=60000, wait_until="networkidle")

            # 2. Open the Reviews Panel
            try:
                # Target the "Reviews" tab specifically
                review_btn = page.get_by_role("button", name=re.compile(r"Reviews", re.IGNORECASE)).first
                await review_btn.wait_for(timeout=10000)
                await review_btn.click()
                logger.info("✅ Clicked Reviews button")
                await page.wait_for_timeout(3000)
            except Exception as e:
                logger.warning(f"⚠️ Could not click Reviews button: {e}. Attempting direct extraction.")

            # 3. Targeted Internal Scrolling
            # Google Maps reviews live inside a specific scrollable div
            scrollable_selector = 'div[role="main"] div[tabindex="-1"]'
            
            last_count = 0
            for i in range(25):  # Loop to reach 200+ reviews
                await page.evaluate(f'''
                    const scrollable = document.querySelector('div[role="main"] div[tabindex="-1"]');
                    if (scrollable) {{
                        scrollable.scrollTop = scrollable.scrollHeight;
                    }}
                ''')
                
                await page.wait_for_timeout(2000)
                
                current_elements = await page.query_selector_all('div.jftiEf')
                current_count = len(current_elements)
                logger.info(f"🔄 Scrolling loop {i+1}: Found {current_count} reviews")
                
                if current_count >= limit:
                    break
                if current_count == last_count and i > 5:
                    break
                last_count = current_count

            # 4. Data Extraction (Fixed Variable Typo)
            final_elements = await page.query_selector_all('div.jftiEf')
            logger.info(f"🧐 Processing {len(final_elements)} items for extraction...")

            for r in final_elements[:limit]:
                try:
                    # Expand long reviews
                    more_btn = await r.query_selector('button:has-text("More")')
                    if more_btn:
                        await more_btn.click()

                    text_el = await r.query_selector('.wiI7pd')
                    author_el = await r.query_selector('.d4r55')
                    rating_el = await r.query_selector('span.kvMYJc')
                    
                    text = await text_el.inner_text() if text_el else "No comment"
                    author = await author_el.inner_text() if author_el else "Google User"
                    
                    # Extract numeric rating from aria-label
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
                except Exception as e:
                    logger.error(f"Error parsing single review: {e}")
                    continue
            
            await browser.close()
            logger.info(f"✨ SUCCESS: Collected {len(reviews)} reviews for database.")

    except Exception as e:
        logger.error(f"❌ Scraper Critical Failure: {str(e)}")
    
    return reviews
