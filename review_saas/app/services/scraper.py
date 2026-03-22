# app/services/scraper.py

import asyncio
import logging
import random
from datetime import datetime
from typing import List, Dict, Any

from playwright.async_api import async_playwright
from playwright_stealth import stealth_async
from selectolax.parser import HTMLParser
from fake_useragent import UserAgent
from tenacity import retry, stop_after_attempt, wait_exponential

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("scraper")

class GoogleReviewScraper:
    def __init__(self):
        self.ua = UserAgent()
        # Current high-accuracy selectors for the Google Review Dialog
        self.selectors = {
            "review_container": ".jftiEf",
            "text": ".wi7Cbe",
            "rating": ".kv9pPn",
            "date": ".rsqaWe",
            "more_button": "button.w8B6B" # "More" button for long reviews
        }

    def _parse_reviews(self, html_content: str) -> List[Dict[str, Any]]:
        tree = HTMLParser(html_content)
        reviews = []
        
        for node in tree.css(self.selectors["review_container"]):
            text_node = node.css_first(self.selectors["text"])
            rating_node = node.css_first(self.selectors["rating"])
            date_node = node.css_first(self.selectors["date"])
            
            # Extract numerical rating from aria-label (e.g., "5 stars")
            raw_rating = rating_node.attributes.get("aria-label", "0") if rating_node else "0"
            rating_value = "".join(filter(str.isdigit, raw_rating))
            
            review_data = {
                "text": text_node.text(strip=True) if text_node else "",
                "rating": rating_value if rating_value else "0",
                "date": date_node.text(strip=True) if date_node else "Unknown",
                "extracted_at": datetime.utcnow().isoformat()
            }
            
            if review_data["text"]:
                reviews.append(review_data)
                
        return reviews

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=4, max=10))
    async def run(self, target_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        async with async_playwright() as p:
            # Launch with Railway-optimized flags
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox", 
                    "--disable-setuid-sandbox", 
                    "--disable-dev-shm-usage"
                ]
            )
            
            context = await browser.new_context(
                user_agent=self.ua.random,
                viewport={'width': 1280, 'height': 800}
            )
            page = await context.new_page()
            await stealth_async(page)
            
            # The "Golden" URL for Place IDs: This opens the reviews modal directly
            # format: https://www.google.com/maps/search/?api=1&query=Google&query_place_id={place_id}
            url = f"https://www.google.com/maps/search/?api=1&query=Google&query_place_id={target_id}"
            
            logger.info(f"🚀 Navigating to Place ID: {target_id}")
            
            try:
                await page.goto(url, wait_until="networkidle", timeout=60000)
                
                # Step 1: Click the "Reviews" tab if it's not open (Maps often opens 'Overview' first)
                # This selector targets the "Reviews" text specifically
                try:
                    review_tab_selector = "button[aria-label*='Reviews']"
                    await page.wait_for_selector(review_tab_selector, timeout=5000)
                    await page.click(review_tab_selector)
                    await asyncio.sleep(2)
                except:
                    logger.info("ℹ️ Reviews tab might already be open or layout is direct.")

                # Step 2: Scrolling logic
                # We target the specific scrollable div for reviews
                scrollable_div = ".m67Bv" 
                
                reviews_found = 0
                scroll_attempts = 0
                max_scrolls = 15

                while reviews_found < limit and scroll_attempts < max_scrolls:
                    # Scroll down inside the review pane
                    await page.mouse.wheel(0, 3000)
                    await asyncio.sleep(1.5)
                    
                    # Count currently visible reviews
                    current_content = await page.content()
                    temp_tree = HTMLParser(current_content)
                    reviews_found = len(temp_tree.css(self.selectors["review_container"]))
                    
                    scroll_attempts += 1
                    logger.info(f"⏳ Scrolling... Found {reviews_found}/{limit} reviews.")

                # Step 3: Parse and Return
                final_content = await page.content()
                results = self._parse_reviews(final_content)
                
                await browser.close()
                logger.info(f"✅ Success! Extracted {len(results)} reviews.")
                return results[:limit]

            except Exception as e:
                logger.error(f"❌ Scraper Failure: {str(e)}")
                if 'browser' in locals():
                    await browser.close()
                return []

async def fetch_reviews(place_id: str, limit: int = 10):
    scraper = GoogleReviewScraper()
    return await scraper.run(target_id=place_id, limit=limit)
