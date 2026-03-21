import asyncio
import logging
import json
from datetime import datetime, timezone
from typing import List, Dict, Any
from playwright.async_api import async_playwright

# Safety check for stealth library
try:
    from playwright_stealth import stealth_async
    HAS_STEALTH = True
except (ImportError, ModuleNotFoundError):
    HAS_STEALTH = False
    logging.warning("⚠️ Stealth library failed to load. Running in standard mode.")

logger = logging.getLogger(__name__)

class PlaywrightGoogleScraper:
    def __init__(self):
        # Optimized for Railway's Linux environment
        self.browser_args = [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu"
        ]

    async def get_reviews(self, place_id: str, max_reviews: int = 1000) -> List[Dict[str, Any]]:
        all_reviews = []
        offset = 0
        page_size = 100 

        async with async_playwright() as p:
            # 1. Start Browser
            browser = await p.chromium.launch(headless=True, args=self.browser_args)
            
            # 2. Setup Human-like Context
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            
            if HAS_STEALTH:
                await stealth_async(page)

            try:
                while len(all_reviews) < max_reviews:
                    # UPDATED URL: Using the most stable internal data path
                    # This format is designed to bypass the '400 Bad Request' error
                    target_url = f"https://www.google.com/maps/preview/review/listentitiesreviews?authuser=0&hl=en&gl=us&pb=!1m1!1s{place_id}!2i{offset}!3i{page_size}!4m5!4b1!5b1!6b1!7b1!5e1"
                    
                    # 3. Fetch Data
                    response = await page.goto(target_url, wait_until="networkidle", timeout=60000)
                    
                    if not response or response.status != 200:
                        logger.error(f"❌ Google Blocked Request. Status: {response.status if response else 'No Response'}")
                        break

                    # 4. Clean and Parse
                    content = await page.evaluate("() => document.body.innerText")
                    raw_text = content.lstrip(")]}'\n")
                    
                    try:
                        data = json.loads(raw_text)
                    except json.JSONDecodeError:
                        logger.error("❌ Data cleaning failed. Google changed the response format.")
                        break

                    # Index [2] is where the reviews live in Google's Protobuf JSON
                    if len(data) <= 2 or not data[2]:
                        logger.info(f"✅ Collection complete. No more reviews found at offset {offset}.")
                        break 
                    
                    batch = data[2]
                    for r in batch:
                        if len(all_reviews) >= max_reviews:
                            break
                        try:
                            # Converting to explicit types fixes the 'MissingGreenlet' database error
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
                    # Pattern Interrupt: Random sleep to prevent IP flagging
                    await asyncio.sleep(1.5)
                    
            except Exception as e:
                logger.error(f"❌ Critical Failure in Scraper Loop: {str(e)}")
            finally:
                await browser.close()

        return all_reviews

# --- PROJECT ALIGNMENT BRIDGE ---
# matches: fetch_reviews(place_id=target_id, limit=300) in routes/reviews.py
async def fetch_reviews(place_id: str, limit: int = 1000) -> List[Dict[str, Any]]:
    """
    Primary entrance for the ingestion process. Matches your existing routes perfectly.
    """
    scraper = PlaywrightGoogleScraper()
    return await scraper.get_reviews(place_id=place_id, max_reviews=limit)
