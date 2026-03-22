# app/services/scraper.py

import asyncio
import logging
import random
import re
from datetime import datetime, timezone
from typing import List, Dict, Any

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from playwright_stealth import Stealth
from fake_useragent import UserAgent
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger("scraper")

@retry(
    stop=stop_after_attempt(3), # Reduced to 3 to save Railway resources
    wait=wait_exponential(multiplier=1.2, min=4, max=20),
    retry=retry_if_exception_type((PlaywrightTimeoutError, Exception)),
    before_sleep=lambda rs: logger.info(f"Retrying scrape... attempt {rs.attempt_number}")
)
async def fetch_reviews(
    place_id: str, # Matches your route's 'place_id' argument
    limit: int = 100,
    sort_by_newest: bool = True,
    headless: bool = True,
) -> List[Dict[str, Any]]:
    
    # Generate the URL from the ID
    place_url = f"https://www.google.com/maps/search/?api=1&query_place_id={place_id}"
    all_reviews: List[Dict[str, Any]] = []
    ua = UserAgent()

    async with async_playwright() as p:
        # Use modern Stealth v2.0
        async with Stealth().use_async(p) as stealth_p:
            browser = await stealth_p.chromium.launch(
                headless=headless,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--single-process", # CRITICAL for Railway
                    "--js-flags='--max-old-space-size=256'" # Limits RAM usage
                ]
            )

            context = await browser.new_context(
                user_agent=ua.random,
                viewport={"width": 1280, "height": 720},
                locale="en-US"
            )

            page = await context.new_page()

            try:
                logger.info(f"🚀 Playwright starting for: {place_id}")
                await page.goto(place_url, wait_until="networkidle", timeout=60000)

                # Cookie handling
                try:
                    await page.get_by_role("button", name=re.compile(r"(Accept|Agree|OK|قبول)", re.I)).click(timeout=5000)
                except: pass

                # Wait for review containers
                await page.wait_for_selector('[data-review-id]', timeout=10000)

                # Parsing logic
                review_els = await page.query_selector_all('[data-review-id]')
                for el in review_els[:limit]:
                    # ... (Your existing parsing logic for rating, text, author)
                    # Note: Ensure your parsing logic matches the elements found on the page
                    pass 

                # Dummy response for demonstration - replace with your loop results
                all_reviews.append({"review_id": "test", "text": "Scraped successfully", "rating": 5})

            finally:
                await context.close()
                await browser.close()

    return all_reviews
