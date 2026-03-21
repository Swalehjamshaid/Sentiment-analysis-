import asyncio
import random
from datetime import datetime
from typing import List, Dict, Any

from playwright.async_api import async_playwright
from playwright_stealth import stealth_async
from selectolax.parser import HTMLParser
from fake_useragent import UserAgent
from tenacity import retry, stop_after_attempt, wait_exponential
from loguru import logger

class GoogleReviewScraper:
    def __init__(self):
        self.ua = UserAgent()
        # Common Google Maps selectors for reviews
        self.selectors = {
            "container": ".jftiEf",
            "text": ".wi7Cbe",
            "rating": ".kv9pPn",
            "date": ".rsqaWe"
        }

    def _parse_reviews(self, html_content: str) -> List[Dict[str, Any]]:
        """Parses the raw HTML using Selectolax for high-speed extraction."""
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
            
            if review_data["text"]:  # Only keep reviews with actual content
                reviews.append(review_data)
        
        return reviews

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10)
    )
    async def run(self, company_name: str, max_reviews: int = 10) -> List[Dict[str, Any]]:
        """
        Executes the scraping mission. 
        Headless mode is handled via launch arguments to fix 'Ghost Protocol' error.
        """
        async with async_playwright() as p:
            try:
                # ✅ FIX: 'set_headless' is not an attribute. Use launch parameters.
                # We use --no-sandbox for Railway/Docker compatibility.
                browser = await p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
                )
                
                context = await browser.new_context(
                    user_agent=self.ua.random,
                    viewport={'width': 1920, 'height': 1080}
                )
                
                page = await context.new_page()
                await stealth_async(page)
                
                logger.info(f"🚀 Starting Playwright scraper for: {company_name}")
                
                # Search for the business on Google Maps
                search_query = company_name.replace(" ", "+")
                url = f"https://www.google.com/maps/search/{search_query}"
                
                await page.goto(url, wait_until="networkidle")
                
                # Wait for the result or the list to appear
                try:
                    # Attempt to find and click the 'Reviews' tab if it's a direct business match
                    reviews_tab = page.get_by_role("tab", name="Reviews")
                    if await reviews_tab.is_visible():
                        await reviews_tab.click()
                        await page.wait_for_timeout(2000)
                except Exception:
                    logger.warning(f"⚠️ Could not find explicit Reviews tab for {company_name}, trying direct scroll.")

                # Scroll to load more reviews
                for _ in range(2): # Minimal scrolling for the initial test
                    await page.mouse.wheel(0, 2000)
                    await asyncio.sleep(random.uniform(1.5, 3.0))

                content = await page.content()
                results = self._parse_reviews(content)
                
                await browser.close()
                
                logger.info(f"🚀 Mission Success: {len(results)} reviews with actual text delivered.")
                return results[:max_reviews]

            except Exception as e:
                # Capture the specific failure for the logs
                logger.error(f"❌ Ghost Protocol Failure: {str(e)}")
                # Re-raise for tenacity to handle retries if it's a transient error
                raise e

# Helper function to be called by your API router
async def get_reviews(location: str):
    scraper = GoogleReviewScraper()
    try:
        return await scraper.run(location)
    except Exception:
        return []
