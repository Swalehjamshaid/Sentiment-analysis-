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

# Setup logging for Railway Deploy Logs
logger = logging.getLogger("scraper")

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1.2, min=4, max=20),
    retry=retry_if_exception_type((PlaywrightTimeoutError, Exception)),
    before_sleep=lambda rs: logger.info(f"Retrying scrape... attempt {rs.attempt_number}")
)
async def fetch_reviews(
    place_id: str, 
    limit: int = 100,
    sort_by_newest: bool = True,
    headless: bool = True,
) -> List[Dict[str, Any]]:
    """
    Complete Google Maps Scraper for ReviewSaaS.
    Bypasses bot detection and handles Railway memory constraints.
    """
    # Direct URL for the specific Place ID
    place_url = f"https://www.google.com/maps/search/?api=1&query=Google&query_place_id={place_id}"
    all_reviews: List[Dict[str, Any]] = []
    ua = UserAgent()

    async with async_playwright() as p:
        # Launch Chromium with memory-saving flags for Railway
        browser = await p.chromium.launch(
            headless=headless,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--single-process",
            ],
            timeout=90000,
        )

        # Create a browser context
        context = await browser.new_context(
            user_agent=ua.random,
            viewport={"width": 1280, "height": 720},
            locale="en-US",
            timezone_id="Asia/Karachi",
        )

        # --- UNIVERSAL STEALTH SETUP ---
        # This handles the version differences in playwright-stealth
        try:
            stealth = Stealth()
            await stealth.setup_async(context)
        except Exception:
            try:
                await Stealth(context).setup_async()
            except Exception as e:
                logger.warning(f"Stealth initialization bypassed: {e}")
        # -------------------------------

        page = await context.new_page()

        try:
            logger.info(f"🚀 Navigating to Place ID: {place_id}")
            await page.goto(place_url, wait_until="networkidle", timeout=60000)

            # 1. Handle Cookie Consent (Common for servers in Singapore/EU)
            try:
                await page.get_by_role("button", name=re.compile(r"(Accept|Agree|OK|قبول|同意)", re.I)).click(timeout=5000)
            except:
                pass

            # 2. Wait for the core review element
            await page.wait_for_selector('[data-review-id]', timeout=15000)

            # 3. Scrolling Logic to reach the 'limit'
            last_count = 0
            for scroll_step in range(25):
                review_elements = await page.query_selector_all('[data-review-id]')
                current_count = len(review_elements)
                
                if current_count >= limit or (current_count > 0 and current_count == last_count):
                    break
                
                last_count = current_count
                # Scroll down the review panel
                await page.mouse.wheel(0, 4000)
                await asyncio.sleep(random.uniform(1.5, 3.0))

            # 4. Parsing the Data
            final_elements = await page.query_selector_all('[data-review-id]')
            logger.info(f"🧐 Found {len(final_elements)} reviews. Parsing now...")

            for el in final_elements[:limit]:
                try:
                    # Review ID
                    r_id = await el.get_attribute("data-review-id") or f"gen_{random.randint(1,99999)}"
                    
                    # Rating extraction
                    star_el = await el.query_selector('[aria-label*="star"]')
                    rating_val = 5
                    if star_el:
                        aria_text = await star_el.get_attribute("aria-label")
                        match = re.search(r"(\d)", aria_text)
                        if match: 
                            rating_val = int(match.group(1))

                    # Text extraction (using common Google Maps classes)
                    text_el = await el.query_selector('.wiI7pd, .MyEned, .K7oBnd')
                    review_body = (await text_el.inner_text()).strip() if text_el else ""

                    # Skip empty reviews
                    if not review_body:
                        continue

                    # Author Name
                    author_el = await el.query_selector('.d4r55, .fontHeadlineSmall, .TSUbDb')
                    author_name = (await author_el.inner_text()).strip() if author_el else "Google User"

                    all_reviews.append({
                        "review_id": r_id,
                        "rating": rating_val,
                        "text": review_body,
                        "author": author_name,
                        "extracted_at": datetime.now(timezone.utc).isoformat(),
                    })
                except Exception:
                    continue

        except Exception as e:
            logger.error(f"❌ Scraper failed for {place_id}: {e}")
            raise # Tenacity will catch this and retry
        finally:
            await context.close()
            await browser.close()

    logger.info(f"✅ Success: Extracted {len(all_reviews)} reviews for {place_id}")
    return all_reviews

# Local test block
if __name__ == "__main__":
    import json
    # Replace with a real Place ID to test locally
    test_id = "ChIJDVYKpFEEGTkRp_XASXZ21Tc" 
    results = asyncio.run(fetch_reviews(place_id=test_id, limit=10))
    print(json.dumps(results, indent=2))
