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
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1.2, min=4, max=20),
    retry=retry_if_exception_type((PlaywrightTimeoutError, Exception)),
    before_sleep=lambda rs: logger.info(f"Retrying scrape... attempt {rs.attempt_number}")
)
async def fetch_reviews(
    place_id: str,         # Updated to match the keyword argument 'place_id' from your route
    limit: int = 100,
    sort_by_newest: bool = True,
    headless: bool = True,
) -> List[Dict[str, Any]]:
    """
    Fetch Google Maps reviews using Playwright + Railway-optimized Chromium settings.
    """
    # Build the URL from the place_id provided by the database
    place_url = f"https://www.google.com/maps/search/?api=1&query_place_id={place_id}"
    
    all_reviews: List[Dict[str, Any]] = []
    ua = UserAgent()

    async with async_playwright() as p:
        # Launch Chromium with Railway memory-saving flags
        browser = await p.chromium.launch(
            headless=headless,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage", # Essential for Railway/Docker
                "--disable-gpu",
                "--single-process",        # Reduces RAM overhead
            ],
            timeout=90000,
        )

        # Create context and apply Stealth
        context = await browser.new_context(
            user_agent=ua.random,
            viewport={"width": 1280, "height": 720},
            locale="en-US",
            timezone_id="Asia/Karachi",
        )
        
        # CORRECT STEALTH IMPLEMENTATION for v2.0+
        stealth = Stealth(context)
        await stealth.setup_async()

        page = await context.new_page()

        try:
            logger.info(f"🚀 Navigating to: {place_url}")
            await page.goto(place_url, wait_until="networkidle", timeout=60000)

            # Handle Cookie Consent
            try:
                await page.get_by_role("button", name=re.compile(r"(Accept|Agree|OK|قبول|同意)", re.I)).click(timeout=5000)
            except:
                pass

            # Wait for any element with a review ID to appear
            await page.wait_for_selector('[data-review-id]', timeout=15000)

            # Scroll logic
            last_count = 0
            for _ in range(20): # Number of scroll attempts
                els = await page.query_selector_all('[data-review-id]')
                current = len(els)
                if current >= limit or (current > 0 and current == last_count):
                    break
                last_count = current
                
                # Scroll the review pane specifically
                await page.mouse.wheel(0, 5000)
                await asyncio.sleep(random.uniform(1.5, 3.0))

            # Parse the results
            review_els = await page.query_selector_all('[data-review-id]')
            logger.info(f"🧐 Found {len(review_els)} elements. Parsing up to {limit}...")

            for el in review_els[:limit]:
                try:
                    r_id = await el.get_attribute("data-review-id") or f"gen_{random.randint(1,99999)}"
                    
                    # Extract Rating
                    star_el = await el.query_selector('[aria-label*="star"]')
                    rating = 5
                    if star_el:
                        aria = await star_el.get_attribute("aria-label")
                        m = re.search(r"(\d)", aria)
                        if m: rating = int(m.group(1))

                    # Extract Text
                    text_el = await el.query_selector('.wiI7pd, .MyEned')
                    review_text = (await text_el.inner_text()).strip() if text_el else ""

                    if not review_text: continue

                    # Extract Author
                    author_el = await el.query_selector('.d4r55, .fontHeadlineSmall')
                    author_name = (await author_el.inner_text()).strip() if author_el else "Google User"

                    all_reviews.append({
                        "review_id": r_id,
                        "rating": rating,
                        "text": review_text,
                        "author": author_name,
                        "extracted_at": datetime.now(timezone.utc).isoformat(),
                    })
                except Exception as parse_err:
                    continue

        except Exception as e:
            logger.error(f"❌ Scrape failed: {e}")
            raise # Re-raise for Tenacity to retry
        finally:
            await context.close()
            await browser.close()

    return all_reviews
