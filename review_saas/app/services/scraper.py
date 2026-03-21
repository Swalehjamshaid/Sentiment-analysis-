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

# Fallback to standard logging since loguru is missing in your env
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
    async def run(self, company_name: str, max_reviews: int = 10) -> List[Dict[str, Any]]:
        async with async_playwright() as p:
            try:
                # ✅ FIX: Headless set correctly for Playwright 1.49.0
                browser = await p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
                )
                
                context = await browser.new_context(user_agent=self.ua.random)
                page = await context.new_page()
                await stealth_async(page)
                
                logger.info(f"🚀 Starting Playwright scraper for: {company_name}")
                
                search_query = company_name.replace(" ", "+")
                url = f"https://www.google.com/maps/search/{search_query}"
                
                await page.goto(url, wait_until="networkidle")
                
                # Simple scroll to trigger content load
                await page.mouse.wheel(0, 2000)
                await asyncio.sleep(2)

                content = await page.content()
                results = self._parse_reviews(content)
                
                await browser.close()
                logger.info(f"✅ Mission Success: {len(results)} reviews delivered.")
                return results[:max_reviews]

            except Exception as e:
                logger.error(f"❌ Ghost Protocol Failure: {str(e)}")
                return []

# ✅ This matches the import in your app/routes/reviews.py
async def fetch_reviews(location: str):
    scraper = GoogleReviewScraper()
    return await scraper.run(location)
