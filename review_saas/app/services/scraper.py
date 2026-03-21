import asyncio
import logging
import json
from datetime import datetime, timezone
from typing import List, Dict, Any
from playwright.async_api import async_playwright

# Standard logging
logger = logging.getLogger(__name__)

class PlaywrightGoogleScraper:
    def __init__(self):
        self.browser_args = [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-setuid-sandbox"
        ]

    async def get_reviews(self, place_id: str, max_reviews: int = 1000) -> List[Dict[str, Any]]:
        all_reviews = []
        
        async with async_playwright() as p:
            # Launching a high-performance headless browser
            browser = await p.chromium.launch(headless=True, args=self.browser_args)
            
            # Using a mobile context to stay "Grey Hat" and fast
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 Safari/604.1"
            )
            page = await context.new_page()

            # The internal Google Maps review URL
            # We use the 'pb' logic inside the URL to request 100 reviews at a time
            offset = 0
            page_size = 100

            try:
                while len(all_reviews) < max_reviews:
                    target_url = f"https://www.google.com/maps/preview/review/listentitiesreviews?authuser=0&hl=en&gl=us&pb=!1m1!1s{place_id}!2i{offset}!3i{page_size}!4m5!4b1!5b1!6b1!7b1!5e1"
                    
                    # Navigate to the data URL
                    await page.goto(target_url)
                    
                    # Get the raw text content (Google's JSON)
                    content = await page.content()
                    
                    # Clean the HTML tags Playwright adds to raw text
                    raw_text = await page.evaluate("() => document.querySelector('pre').innerText")
                    raw_text = raw_text.lstrip(")]}'\n")
                    
                    data = json.loads(raw_text)

                    if len(data) <= 2 or not data[2]:
                        break 
                    
                    batch = data[2]
                    for r in batch:
                        if len(all_reviews) >= max_reviews:
                            break
                        try:
                            all_reviews.append({
                                "review_id": str(r[0]),
                                "rating": int(r[4]),
                                "text": str(r[3]) if r[3] else "",
                                "author": str(r[1][4][0][4]) if (len(r) > 1 and r[1]) else "Anonymous",
                                "timestamp_ms": r[27],
                                "date": datetime.fromtimestamp(r[27]/1000, tz=timezone.utc).isoformat()
                            })
                        except (IndexError, TypeError):
                            continue

                    if len(batch) < page_size:
                        break

                    offset += page_size
                    # Human-like delay
                    await asyncio.sleep(1)
                    
            except Exception as e:
                logger.error(f"Playwright Scraper Error: {str(e)}")
            finally:
                await browser.close()

        return all_reviews

# --- PROJECT ALIGNMENT BRIDGE ---
async def fetch_reviews(place_id: str, limit: int = 1000) -> List[Dict[str, Any]]:
    """
    Standard entry point for your FastAPI routes.
    Matches: fetch_reviews(place_id=target_id, limit=300)
    """
    scraper = PlaywrightGoogleScraper()
    return await scraper.get_reviews(place_id=place_id, max_reviews=limit)
