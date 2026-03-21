# app/services/scraper.py

import asyncio
import random
import logging
from datetime import datetime
from typing import List, Dict, Any

from playwright.async_api import async_playwright
from playwright_stealth import stealth_async
from selectolax.parser import HTMLParser
from fake_useragent import UserAgent
from tenacity import retry, stop_after_attempt, wait_exponential

# Use standard logging to avoid ModuleNotFound errors on Railway
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("scraper")

class GoogleReviewScraper:
    def __init__(self):
        self.ua = UserAgent()
        self.selectors = {
            "container": ".jftiEf",
            "text": ".wi7Cbe",
            "rating": ".kv9pPn",
            "date": ".rsqaWe"
        }

    def _parse_reviews(self, html_content: str) -> List[Dict[str, Any]]:
        tree = HTMLParser(html_content)
        reviews = []
        for node in tree.css(self.selectors["container"]):
            text_node = node.css_first(self.selectors["text"])
            rating_node = node.css_first(self.selectors["rating"])
            date_node = node.css_first(self.selectors["date"])
            
            review_data = {
                "text": text_node.text(strip=True) if text_node else "",
                "rating": rating_node.attributes.get("aria-label", "0") if rating_node else "0",
                "date": date_node.text(strip=True) if date_node else "Unknown",
                "extracted_at": datetime.utcnow().isoformat()
            }
            if review_data["text"]:
                reviews.append(review_data)
        return reviews

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    async def run(self, target_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        async with async_playwright() as p:
            try:
                # Correct Headless Launch for Railway
                browser = await p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
                )
                
                context = await browser.new_context(user_agent=self.ua.random)
                page = await context.new_page()
                await stealth_async(page)
                
                logger.info(f"🚀 Starting scrape for target: {target_id}")
                
                # If target_id is a place_id, we use the Google Maps CID or search query
                url = f"https://www.google.com/maps/search/?api=1&query=google&query_place_id={target_id}"
                
                await page.goto(url, wait_until="networkidle")
                
                # Small wait for layout
                await asyncio.sleep(2)
                
                # Scroll a few times to get closer to the requested limit
                scroll_count = min(limit // 10, 5) # Cap scrolls for safety
                for _ in range(scroll_count):
                    await page.mouse.wheel(0, 3000)
                    await asyncio.sleep(1.5)

                content = await page.content()
                results = self._parse_reviews(content)
                
                await browser.close()
                logger.info(f"✅ Success: Extracted {len(results)} reviews.")
                return results[:limit]

            except Exception as e:
                logger.error(f"❌ Scraper Failure: {str(e)}")
                return []

# ✅ UPDATED: Function signature now matches what app/routes/reviews.py expects
async def fetch_reviews(place_id: str, limit: int = 10):
    scraper = GoogleReviewScraper()
    return await scraper.run(target_id=place_id, limit=limit)
