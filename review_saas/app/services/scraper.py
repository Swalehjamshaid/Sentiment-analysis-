# app/services/scraper.py
# Updated March 23, 2026 – Aggressive reliability fixes for Railway

import asyncio
import logging
import random
import re
from datetime import datetime, timezone
from typing import List, Dict, Any

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from fake_useragent import UserAgent
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger("scraper")

# =====================================================
# CONFIG
# =====================================================
MAX_ATTEMPTS = 6
GOTO_TIMEOUT = 90000
SCROLL_ATTEMPTS = 20

class ReliableScraper:
    _browser = None
    _playwright = None
    _lock = asyncio.Lock()

    async def _init_browser(self):
        async with self._lock:
            if self._browser and self._browser.is_connected():
                return
            if self._browser:
                await self._browser.close()
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--disable-software-rasterizer",
                    "--disable-background-timer-throttling",
                    "--disable-renderer-backgrounding",
                    "--disable-blink-features=AutomationControlled",
                ]
            )
            logger.info("Browser initialized")

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=4, max=15))
    async def _safe_goto(self, page, url):
        await page.goto(url, wait_until="commit", timeout=GOTO_TIMEOUT)
        await page.wait_for_load_state("domcontentloaded", timeout=30000)
        logger.info(f"Navigated to {page.url} | Title: {await page.title()}")

    async def fetch_reviews(self, place_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        await self._init_browser()

        results = []
        ua = UserAgent().random

        for attempt in range(1, MAX_ATTEMPTS + 1):
            logger.info(f"Attempt {attempt}/{MAX_ATTEMPTS} for place_id {place_id}")

            context = None
            page = None
            try:
                context = await self._browser.new_context(
                    user_agent=ua,
                    viewport={"width": 1366, "height": 768},
                    locale="en-US",
                    timezone_id="Asia/Karachi",
                    bypass_csp=True,
                )
                page = await context.new_page()

                # Stealth basics
                await page.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                    window.chrome = { runtime: {} };
                """)

                # Better URL: direct Maps place link
                url = f"https://www.google.com/maps/place/_/data=!4m2!3m1!1s{place_id}"

                await self._safe_goto(page, url)

                # Save initial screenshot
                ts = datetime.now().strftime("%Y%m%d-%H%M%S")
                await page.screenshot(path=f"/tmp/start-attempt-{attempt}-{ts}.png", full_page=True)

                # Consent
                try:
                    await page.locator('button:has-text("Accept all")').click(timeout=8000)
                except:
                    try:
                        await page.locator('button[aria-label*="Accept"]').click(timeout=5000)
                    except:
                        pass

                # Open Reviews – very aggressive
                review_triggers = [
                    '[aria-label*="Reviews"]',
                    'button:has-text("Reviews")',
                    'button:has-text("Reviews")',
                    'div[role="tab"] [aria-label*="Reviews"]',
                    'button[jsaction*="review"]',
                    '[role="button"] [aria-label*="more reviews"]',
                    'button:has-text("See all reviews")',
                ]

                opened = False
                for sel in review_triggers:
                    try:
                        btn = page.locator(sel)
                        if await btn.is_visible(timeout=6000):
                            await btn.click()
                            logger.info(f"Clicked reviews trigger: {sel}")
                            opened = True
                            await asyncio.sleep(random.uniform(2.5, 4.5))
                            break
                    except:
                        continue

                if not opened:
                    logger.warning("No reviews tab found – trying forced scroll anyway")

                # Wait for any review container
                try:
                    await page.wait_for_selector('div[data-review-id], .jftiEf, [aria-label*="review"]', timeout=15000)
                except:
                    logger.warning("No review container appeared after wait")

                # Scroll aggressively
                for i in range(SCROLL_ATTEMPTS):
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await asyncio.sleep(random.uniform(1.0, 2.8))

                    # Check if loaded something
                    count = len(await page.query_selector_all('div[data-review-id]'))
                    if count > 5 and i > 5:
                        break

                # Extract
                cards = await page.query_selector_all('div[data-review-id], .jftiEf, div[jsaction*="review"], [role="listitem"]')
                logger.info(f"Found {len(cards)} cards")

                for card in cards:
                    try:
                        rid = await card.get_attribute("data-review-id") or f"gen_{random.randint(10000,999999)}"

                        # Rating
                        star = await card.query_selector('[aria-label*="star"], [role="img"][aria-label*="star"]')
                        rating = 5
                        if star:
                            aria = await star.get_attribute("aria-label") or ""
                            m = re.search(r"(\d+)", aria)
                            if m:
                                rating = int(m.group(1))

                        # Text
                        text_els = await card.query_selector_all('span[jsname], .wiI7pd, .MyEned, div[aria-label*="review"] span')
                        text = " ".join([await el.inner_text() for el in text_els if await el.inner_text()])
                        text = re.sub(r'\s+', ' ', text).strip()

                        if len(text) > 50:
                            results.append({
                                "review_id": rid,
                                "rating": rating,
                                "text": text,
                                "author": "Google User",
                                "extracted_at": datetime.now(timezone.utc).isoformat(),
                            })
                    except:
                        continue

                if results:
                    logger.info(f"Success on attempt {attempt}: {len(results)} reviews")
                    break

            except PlaywrightTimeoutError as te:
                logger.error(f"Timeout on attempt {attempt}: {te}")
            except Exception as e:
                logger.error(f"Attempt {attempt} failed: {e}", exc_info=True)
            finally:
                if page:
                    # Final screenshot
                    try:
                        await page.screenshot(path=f"/tmp/end-attempt-{attempt}-{ts}.png", full_page=True)
                    except:
                        pass
                    await page.close()
                if context:
                    await context.close()

            await asyncio.sleep(random.uniform(3, 7))  # Cool down

        return results[:limit]


scraper_instance = ReliableScraper()

async def fetch_reviews(place_id: str, limit: int = 100):
    try:
        return await scraper_instance.fetch_reviews(place_id, limit)
    except Exception as e:
        logger.critical(f"Fatal: {e}")
        return []
