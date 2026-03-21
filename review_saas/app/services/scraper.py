import asyncio
import logging
import json
from datetime import datetime, timezone
from typing import List, Dict, Any
from playwright.async_api import async_playwright

try:
    from playwright_stealth import stealth_async
    HAS_STEALTH = True
except (ImportError, ModuleNotFoundError):
    HAS_STEALTH = False

logger = logging.getLogger(__name__)

class PlaywrightGoogleScraper:
    def __init__(self):
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
            browser = await p.chromium.launch(headless=True, args=self.browser_args)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 Safari/604.1"
            )
            page = await context.new_page()
            
            if HAS_STEALTH:
                await stealth_async(page)

            try:
                while len(all_reviews) < max_reviews:
                    # UPDATED URL FORMAT: Using the direct review search endpoint
                    # This is more stable for international IDs like the one for Lahore
                    target_url = f"https://www.google.com/maps/preview/review/listentitiesreviews?authuser=0&hl=en&gl=us&pb=!1m1!1s{place_id}!2i{offset}!3i{page_size}!4m5!4b1!5b1!6b1!7b1!5e1"
                    
                    response = await page.goto(target_url)
                    
                    # If we get a 400, it means the ID needs the 'ChIJ' logic handled differently
                    if response.status != 200:
                        logger.error(f"Google Status {response.status} at offset {offset}. Trying alternative format...")
                        break

                    content = await page.evaluate("() => document.body.innerText")
                    raw_text = content.lstrip(")]}'\n")
                    
                    try:
                        data = json.loads(raw_text)
                    except json.JSONDecodeError:
                        break

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
                        except (IndexError, TypeError, KeyError):
                            continue

                    if len(batch) < page_size:
                        break

                    offset += page_size
                    await asyncio.sleep(1.0)
                    
            except Exception as e:
                logger.error(f"Scraper Loop Failure: {str(e)}")
            finally:
                await browser.close()

        return all_reviews

async def fetch_reviews(place_id: str, limit: int = 1000) -> List[Dict[str, Any]]:
    scraper = PlaywrightGoogleScraper()
    return await scraper.get_reviews(place_id=place_id, max_reviews=limit)
