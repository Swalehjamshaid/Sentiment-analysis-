import asyncio
import logging
import json
from datetime import datetime, timezone
from typing import List, Dict, Any
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

# Standard logging for your Railway dashboard
logger = logging.getLogger(__name__)

class PlaywrightGoogleScraper:
    def __init__(self):
        # Flags to make Chromium run smoothly on Railway's Linux environment
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
        page_size = 100 # Chunks of 100 is the fastest safe speed

        async with async_playwright() as p:
            # 1. Launch Browser
            browser = await p.chromium.launch(headless=True, args=self.browser_args)
            
            # 2. Setup Stealth Context
            # This makes the browser look like a real desktop Chrome user
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            
            # Apply Stealth to hide Playwright's automated fingerprints
            await stealth_async(page)

            try:
                while len(all_reviews) < max_reviews:
                    # Target Google's internal review endpoint directly
                    target_url = f"https://www.google.com/maps/preview/review/listentitiesreviews?authuser=0&hl=en&gl=us&pb=!1m1!1s{place_id}!2i{offset}!3i{page_size}!4m5!4b1!5b1!6b1!7b1!5e1"
                    
                    # 3. Fetch Data
                    response = await page.goto(target_url)
                    
                    if not response or response.status != 200:
                        logger.error(f"Google blocked request or returned error at offset {offset}. Status: {response.status if response else 'No Response'}")
                        break

                    # 4. Extract and Clean JSON
                    # Google prefixes JSON with )]}' to prevent easy scraping
                    content = await page.evaluate("() => document.body.innerText")
                    raw_text = content.lstrip(")]}'\n")
                    
                    try:
                        data = json.loads(raw_text)
                    except json.JSONDecodeError:
                        logger.error("Failed to decode JSON from Google response.")
                        break

                    if len(data) <= 2 or not data[2]:
                        break # End of reviews found
                    
                    batch = data[2]
                    for r in batch:
                        if len(all_reviews) >= max_reviews:
                            break
                        try:
                            # Mapping to the exact format your database and AI models expect
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

                    # If the batch is smaller than requested, we hit the end of the available reviews
                    if len(batch) < page_size:
                        break

                    offset += page_size
                    # Random delay to mimic a human scrolling and avoid IP bans
                    await asyncio.sleep(1.5)
                    
            except Exception as e:
                logger.error(f"Python Playwright Scraper Error: {str(e)}")
            finally:
                await browser.close()

        return all_reviews

# --- PROJECT ALIGNMENT BRIDGE ---
# matches: fetch_reviews(place_id=target_id, limit=300)
async def fetch_reviews(place_id: str, limit: int = 1000) -> List[Dict[str, Any]]:
    """
    Standard entry point for your project. 
    This naming allows reviews.py to work without any changes.
    """
    scraper = PlaywrightGoogleScraper()
    return await scraper.get_reviews(place_id=place_id, max_reviews=limit)
