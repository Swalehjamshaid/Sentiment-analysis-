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
    stop=stop_after_attempt(2), # Reduced to avoid Railway timeouts
    wait=wait_exponential(multiplier=2, min=5, max=15),
    retry=retry_if_exception_type((PlaywrightTimeoutError, Exception)),
    before_sleep=lambda rs: logger.info(f"🔄 Retrying... attempt {rs.attempt_number}")
)
async def fetch_reviews(place_id: str, limit: int = 100) -> List[Dict[str, Any]]:
    # This URL format is the most stable for Place IDs globally
    place_url = f"https://www.google.com/maps/search/?api=1&query=google&query_place_id={place_id}"
    all_reviews = []
    ua = UserAgent()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage", "--single-process"]
        )
        context = await browser.new_context(user_agent=ua.random, locale="en-US")
        
        # Robust Stealth Setup
        try:
            await Stealth(context).setup_async()
        except:
            pass

        page = await context.new_page()

        try:
            logger.info(f"🌐 Navigating to place_id: {place_id}")
            # Increase timeout to 90 seconds for slow maps loading
            await page.goto(place_url, wait_until="networkidle", timeout=90000)

            # 1. Handle the "Consent" or "I Agree" button (CRITICAL for servers)
            try:
                consent_btn = page.get_by_role("button", name=re.compile(r"(Accept|Agree|OK|قبول|Agree all)", re.I))
                if await consent_btn.is_visible(timeout=5000):
                    await consent_btn.click()
                    await asyncio.sleep(2)
            except:
                pass

            # 2. Click the "Reviews" tab if it's not visible
            try:
                review_tab = page.get_by_role("button", name=re.compile(r"Reviews", re.I))
                await review_tab.click(timeout=10000)
                await asyncio.sleep(3)
            except:
                logger.info("ℹ️ Reviews tab click skipped or not found.")

            # 3. Wait for the review items (Increased timeout)
            await page.wait_for_selector('[data-review-id]', timeout=30000)

            # 4. Scroll and Parse
            last_count = 0
            for _ in range(15):
                review_els = await page.query_selector_all('[data-review-id]')
                if len(review_els) >= limit or (len(review_els) > 0 and len(review_els) == last_count):
                    break
                last_count = len(review_els)
                await page.mouse.wheel(0, 3000)
                await asyncio.sleep(2)

            for el in review_els[:limit]:
                try:
                    r_id = await el.get_attribute("data-review-id")
                    text_el = await el.query_selector(".wiI7pd, .MyEned")
                    body = await text_el.inner_text() if text_el else ""
                    
                    if body:
                        all_reviews.append({
                            "review_id": r_id,
                            "rating": 5, # Simplified for now
                            "text": body.strip(),
                            "author": "Google User",
                            "extracted_at": datetime.now(timezone.utc).isoformat()
                        })
                except:
                    continue

        finally:
            await context.close()
            await browser.close()

    return all_reviews
