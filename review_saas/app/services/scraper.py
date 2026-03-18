# filename: review_saas/app/services/scraper.py

import asyncio
import logging
import re
from datetime import datetime
from typing import List, Dict, Any
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)


async def fetch_reviews(place_id: str, limit: int = 300, skip: int = 0) -> List[Dict[str, Any]]:
    reviews = []
    # Use the more standard Maps URL which is less likely to trigger bot detection
    place_url = f"https://www.google.com/maps/search/?api=1&query=Google&query_place_id={place_id}"

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
            )
            
            context = await browser.new_context(
                viewport={'width': 1280, 'height': 900},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                locale="en-US"
            )
            
            page = await context.new_page()
            logger.info(f"🚀 Navigating to Place ID: {place_id}")

            # 1. Load Page
            await page.goto(place_url, wait_until="networkidle", timeout=60000)

            # 2. BREAK CONSENT WALL
            try:
                consent_selectors = ["Accept all", "Agree", "Allow", "Accept"]
                for btn_text in consent_selectors:
                    btn = page.get_by_role("button", name=re.compile(btn_text, re.IGNORECASE)).first
                    if await btn.is_visible(timeout=3000):
                        await btn.click()
                        logger.info(f"✅ Bypassed Consent with: {btn_text}")
                        await page.wait_for_timeout(2000)
                        break
            except Exception:
                logger.info("Consent wall not found; proceeding.")

            # 3. OPEN REVIEWS PANEL
            review_triggered = False
            review_locators = [
                'button[aria-label*="Reviews"]',
                'button:has-text("Reviews")',
                'div[role="tab"]:has-text("Reviews")',
                '.hh7Vgc'
            ]

            for selector in review_locators:
                try:
                    target = page.locator(selector).first
                    if await target.is_visible(timeout=5000):
                        await target.click()
                        review_triggered = True
                        logger.info(f"✅ Reviews panel opened via {selector}")
                        await page.wait_for_selector('div[role="article"]', timeout=15000)
                        break
                except Exception:
                    continue

            if not review_triggered:
                logger.warning("Could not find 'Reviews' tab.")

            # 4. SCROLL REVIEWS PANEL
            last_count = 0
            for i in range(30):
                await page.evaluate('''
                    const scrollable = document.querySelector('div[role="feed"]');
                    if (scrollable) {
                        scrollable.scrollBy(0, 2000);
                    } else {
                        window.scrollBy(0, 1000);
                    }
                ''')

                await page.wait_for_timeout(2000)

                elements = await page.query_selector_all('div[role="article"]')
                current_count = len(elements)
                logger.info(f"🔄 Loop {i+1}: Found {current_count} reviews")

                if current_count >= limit:
                    break

                if current_count == last_count and i > 5:
                    break

                last_count = current_count

            # 5. EXTRACT DATA
            final_elements = await page.query_selector_all('div[role="article"]')
            logger.info(f"🧐 Extracting data from {len(final_elements)} items...")

            for r in final_elements[:limit]:
                try:
                    more_btn = await r.query_selector('button:has-text("More")')
                    if more_btn:
                        await more_btn.click()
                        await page.wait_for_timeout(200)

                    text_el = await r.query_selector('.wiI7pd')
                    author_el = await r.query_selector('.d4r55')
                    rating_el = await r.query_selector('span[role="img"]')

                    if not author_el:
                        continue

                    text = await text_el.inner_text() if text_el else ""
                    author = await author_el.inner_text() if author_el else "Google User"

                    rating_raw = await rating_el.get_attribute("aria-label") if rating_el else "0"
                    rating_match = re.search(r'(\d+)', rating_raw)
                    rating = int(rating_match.group(1)) if rating_match else 0

                    reviews.append({
                        "review_id": f"pw_{hash(text + author + str(datetime.now().timestamp()))}",
                        "rating": rating,
                        "text": text,
                        "author_name": author,
                        "google_review_time": datetime.utcnow().isoformat()
                    })

                except Exception as e:
                    logger.debug(f"Row skip: {e}")
                    continue

            await browser.close()
            logger.info(f"✨ MISSION COMPLETE: Collected {len(reviews)} reviews.")

    except Exception as e:
        logger.error(f"❌ Scraper Critical Failure: {str(e)}")

    return reviews
