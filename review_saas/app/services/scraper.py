# app/services/scraper.py

import asyncio
import logging
from datetime import datetime
from typing import List, Dict, Any

from playwright.async_api import async_playwright
from playwright_stealth import stealth_async
from selectolax.parser import HTMLParser
from fake_useragent import UserAgent
from tenacity import retry, stop_after_attempt, wait_exponential

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("scraper")

class GoogleReviewScraper:
    def __init__(self):
        self.ua = UserAgent()
        # BROADER SELECTORS: Google often rotates these classes
        self.selectors = {
            "container": [".jftiEf", ".m67Bv", ".W4Efsd"], 
            "text": [".wi7Cbe", ".My579b", ".K7oBnd"],
            "rating": [".kv9pPn", ".f399f"],
            "date": [".rsqaWe", ".P87Y3d"]
        }

    def _parse_reviews(self, html_content: str) -> List[Dict[str, Any]]:
        tree = HTMLParser(html_content)
        reviews = []
        
        # Try each container selector until one works
        container_selector = None
        for sel in self.selectors["container"]:
            if tree.css_first(sel):
                container_selector = sel
                break
        
        if not container_selector:
            return []

        for node in tree.css(container_selector):
            # Try multiple text selectors
            text_node = None
            for ts in self.selectors["text"]:
                text_node = node.css_first(ts)
                if text_node: break
                
            rating_node = node.css_first(self.selectors["rating"][0])
            date_node = node.css_first(self.selectors["date"][0])
            
            review_text = text_node.text(strip=True) if text_node else ""
            
            if review_text:
                reviews.append({
                    "text": review_text,
                    "rating": rating_node.attributes.get("aria-label", "0") if rating_node else "0",
                    "date": date_node.text(strip=True) if date_node else "Unknown",
                    "extracted_at": datetime.utcnow().isoformat()
                })
        return reviews

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=4, max=10))
    async def run(self, target_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
            )
            context = await browser.new_context(user_agent=self.ua.random)
            page = await context.new_page()
            await stealth_async(page)
            
            # MODERN URL: This is the most stable way to call a Place ID
            url = f"https://www.google.com/maps/search/?api=1&query=Google&query_place_id={target_id}"
            
            logger.info(f"🔗 Navigating to: {url}")
            await page.goto(url, wait_until="networkidle", timeout=60000)
            
            # Wait for any review-like content to load
            await asyncio.sleep(5) 

            # Attempt to click "Reviews" tab if it exists
            try:
                await page.click("button[aria-label*='Reviews']", timeout=5000)
                await asyncio.sleep(2)
            except:
                pass

            # Scroll and Parse
            for i in range(min(limit // 5, 10)):
                # Scroll the specific review panel if found, else scroll page
                await page.mouse.wheel(0, 2000)
                await asyncio.sleep(2)
                
                content = await page.content()
                results = self._parse_reviews(content)
                logger.info(f"⏳ Attempt {i+1}: Found {len(results)} reviews so far...")
                
                if len(results) >= limit:
                    break

            await browser.close()
            return results[:limit]

async def fetch_reviews(place_id: str, limit: int = 10):
    scraper = GoogleReviewScraper()
    return await scraper.run(target_id=place_id, limit=limit)
