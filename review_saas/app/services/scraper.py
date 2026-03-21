import asyncio
import logging
import json
from datetime import datetime, timezone
from typing import List, Dict, Any
from playwright.async_api import async_playwright

# Safety import for the stealth library
try:
    from playwright_stealth import stealth_async
    HAS_STEALTH = True
except (ImportError, ModuleNotFoundError):
    HAS_STEALTH = False
    logging.warning("⚠️ Stealth library not found. Proceeding with standard Playwright.")

logger = logging.getLogger(__name__)

class PlaywrightGoogleScraper:
    def __init__(self):
        # Optimized flags for Railway's shared CPU environment
        self.browser_args = [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--single-process" # Reduces RAM usage on Railway
        ]

    async def get_reviews(self, place_id: str, max_reviews: int = 1000) -> List[Dict[str, Any]]:
        all_reviews = []
        offset = 0
        page_size = 100 

        async with async_playwright() as p:
            # 1. Launching Browser
            browser = await p.chromium.launch(headless=True, args=self.browser_args)
            
            # 2. Creating a high-authority Desktop context
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                viewport={'width': 1920, 'height': 1080}
            )
            page = await context.new_page()
            
            if HAS_STEALTH:
                await stealth_async(page)

            try:
                while len(all_reviews) < max_reviews:
                    # UPDATED: Using the most stable internal data endpoint to avoid Status 400
                    # Note the '!1s' prefix before the place_id which is critical for Google Protobuf
                    target_url = f"https://www.google.com/maps/preview/review/listentitiesreviews?authuser=0&hl=en&gl=us&pb=!1m1!1s{place_id}!2i{offset}!3i{page_size}!4m5!4b1!5b1!6b1!7b1!5e1"
                    
                    # 3. Fetching with a longer timeout for Railway stability
                    response = await page.goto(target_url, wait_until="load", timeout=60000)
                    
                    if response.status != 200:
                        logger.error(f"❌ Google returned Status {response.status} at offset {offset}. Stopping.")
                        break

                    # 4. Extracting raw text from the browser's <body>
                    content = await page.evaluate("() => document.body.innerText")
                    
                    # Google's security prefix: )]}'
                    raw_text = content.lstrip(")]}'\n")
                    
                    try:
                        data = json.loads(raw_text)
                    except json.JSONDecodeError:
                        logger.error("❌ Failed to parse JSON. Page layout might have shifted.")
                        break

                    # Index [2] contains the list of review objects
                    if len(data) <= 2 or not data[2]:
                        logger.info(f"✅ Reached the end of reviews at offset {offset}.")
                        break 
                    
                    batch = data[2]
                    for r in batch:
                        if len(all_reviews) >= max_reviews:
                            break
                        try:
                            # Converting to explicit types ensures SQLAlchemy/DB alignment
                            all_reviews.append({
                                "review_id": str(r[0]),
                                "rating": int(r[4]),
                                "text": str(r[3]) if r[3] else "",
                                "author": str(r[1][4][0][4]) if (len(r) > 1 and r[1]) else "Anonymous",
                                "timestamp_ms": r[27],
                                "date": datetime.fromtimestamp(r[27]/1000, tz=timezone.utc).isoformat()
                            })
                        except (IndexError, TypeError, KeyError):
                            continue

                    if len(batch) < page_size:
                        break

                    offset += page_size
                    # Stay under the radar with a 1.5s human-like pause
                    await asyncio.sleep(1.5)
                    
            except Exception as e:
                logger.error(f"❌ Critical Scraper Failure: {str(e)}")
            finally:
                await browser.close()

        return all_reviews

# --- PROJECT ALIGNMENT BRIDGE ---
# This matches your routes/reviews.py call: fetch_reviews(place_id=target_id, limit=300)
async def fetch_reviews(place_id: str, limit: int = 1000) -> List[Dict[str, Any]]:
    """
    Standard entry point. Aligns the external logic with the Playwright Scraper.
    """
    scraper = PlaywrightGoogleScraper()
    return await scraper.get_reviews(place_id=place_id, max_reviews=limit)
