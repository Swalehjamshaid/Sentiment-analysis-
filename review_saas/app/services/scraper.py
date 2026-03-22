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

# Setup logging for Railway output
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("scraper")

class GoogleReviewScraper:
    def __init__(self):
        self.ua = UserAgent()
        # Selectors for Google Maps review elements
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
                # Launching with specific arguments for Linux/Railway containers
                browser = await p.chromium.launch(
                    headless=True,
                    args=[
                        "--no-sandbox", 
                        "--disable-setuid-sandbox", 
                        "--disable-dev-shm-usage",
                        "--disable-gpu",
                        "--no-zygote",
                        "--single-process"
                    ]
                )
                
                context = await browser.new_context(
                    user_agent=self.ua.random,
                    viewport={'width': 1280, 'height': 800}
                )
                page = await context.new_page()
                await stealth_async(page)
                
                logger.info(f"🚀 Scraper started for ID: {target_id}")
                
                # Standard internal Google Review URL
                url = f"https://www.google.com/maps/reviews/data=!4m8!14m7!1m6!1s{target_id}!2s1!3m1!1s1!4m1!1i10"
                
                await page.goto(url, wait_until="networkidle", timeout=60000)
                await asyncio.sleep(2)
                
                # Dynamic scrolling based on requested limit
                scrolls = min(limit // 5, 8) 
                for _ in range(scrolls):
                    await page.mouse.wheel(0, 2000)
                    await asyncio.sleep(1)

                content = await page.content()
                results = self._parse_reviews(content)
                
                await browser.close()
                logger.info(f"✅ Extracted {len(results)} reviews.")
                return results[:limit]

            except Exception as e:
                logger.error(f"❌ Scraper Error: {str(e)}")
                return []

# Entry point function used by the API routes
async def fetch_reviews(place_id: str, limit: int = 10):
    scraper = GoogleReviewScraper()
    return await scraper.run(target_id=place_id, limit=limit)
