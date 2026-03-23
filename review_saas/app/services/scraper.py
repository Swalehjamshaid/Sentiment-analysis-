import asyncio
import logging
import random
import re
from datetime import datetime, timezone
from typing import List, Dict, Any

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from fake_useragent import UserAgent
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type

logger = logging.getLogger("scraper")

# =====================================================
# CONFIG
# =====================================================
MAX_ATTEMPTS = 8                # Reduced to avoid overwhelming crashing browser
MAX_SCROLL_ATTEMPTS = 18
MIN_DELAY = 0.9
MAX_DELAY = 2.5

# =====================================================
# GLOBAL SCRAPER (REUSE + HEALTH CHECK)
# =====================================================
class RobustScraper:
    def __init__(self):
        self._playwright = None
        self._browser = None
        self._lock = asyncio.Lock()
        self._healthy = False

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(5), retry=retry_if_exception_type(Exception))
    async def _init_or_restart_browser(self):
        async with self._lock:
            if self._browser and not self._browser.is_connected():
                logger.warning("Browser connection lost → restarting")
                await self._browser.close()
                self._browser = None

            if not self._browser:
                logger.info("Initializing / restarting browser")
                self._playwright = await async_playwright().start()
                self._browser = await self._playwright.chromium.launch(
                    headless=True,
                    args=[
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-gpu",
                        "--disable-software-rasterizer",
                        "--disable-extensions",
                        "--disable-features=TranslateUI,BlinkGenPropertyTrees,site-per-process",
                        "--disable-background-timer-throttling",
                        "--disable-renderer-backgrounding",
                        "--no-zygote",
                        "--disable-blink-features=AutomationControlled",
                        "--window-size=1366,768",
                    ],
                    timeout=90000,
                )
                self._healthy = True
                logger.info("Browser initialized successfully")

    async def _create_stable_context(self):
        await self._init_or_restart_browser()
        try:
            context = await self._browser.new_context(
                user_agent=UserAgent().random,
                viewport={"width": 1366, "height": 768},
                locale="en-US",
                timezone_id="Asia/Karachi",
                bypass_csp=True,
                java_script_enabled=True,
            )
            return context
        except Exception as e:
            logger.error(f"Context creation failed: {e} → marking browser unhealthy")
            self._healthy = False
            raise

    async def fetch_reviews(self, place_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        await self._init_or_restart_browser()

        results = []
        ua = UserAgent()

        for attempt in range(1, MAX_ATTEMPTS + 1):
            logger.info(f"STRATEGY {attempt}/{MAX_ATTEMPTS} started")

            context = None
            page = None
            try:
                context = await self._create_stable_context()
                page = await context.new_page()

                # Stealth injection
                await page.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                    Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
                    Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
                    window.chrome = { runtime: {} };
                """)

                url = f"https://www.google.com/maps/place/?q=place_id:{place_id}"
                logger.info(f"Navigating: {url}")

                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                await page.wait_for_timeout(random.randint(1500, 3500))

                # Basic page state log
                title = await page.title()
                logger.info(f"Page title: {title}")

                # Consent handling
                try:
                    await page.get_by_role("button", name=re.compile(r"(Accept|Agree|OK|قبول)", re.I)).click(timeout=8000)
                except:
                    pass

                # Try to open reviews section
                review_selectors = [
                    'button[aria-label*="Reviews"]',
                    'div[role="tab"][aria-label*="Reviews"]',
                    'button:has-text("Reviews")',
                    'button[jsaction*="pane.reviewChart.moreReviews"]',
                ]
                for sel in review_selectors:
                    try:
                        await page.locator(sel).click(timeout=10000)
                        await asyncio.sleep(random.uniform(1.8, 3.2))
                        break
                    except:
                        continue

                # Scroll
                for _ in range(MAX_SCROLL_ATTEMPTS):
                    await page.evaluate("window.scrollBy(0, 2800)")
                    await asyncio.sleep(random.uniform(MIN_DELAY, MAX_DELAY))

                # Extract reviews
                cards = await page.query_selector_all('div[data-review-id], .jftiEf, div[jsaction*="review"]')
                logger.info(f"Found {len(cards)} potential review cards")

                temp_results = []
                for card in cards:
                    try:
                        rid = await card.get_attribute("data-review-id") or f"gen_{random.randint(10000,999999)}"

                        # Rating
                        star = await card.query_selector('[aria-label*="star"], [aria-label*="stars"]')
                        rating = 5
                        if star:
                            aria = await star.get_attribute("aria-label") or ""
                            m = re.search(r"(\d+)", aria)
                            if m:
                                rating = int(m.group(1))

                        # Text
                        text_els = await card.query_selector_all('span[jsname], .wiI7pd, .MyEned, span[dir="auto"]')
                        text = " ".join([await el.inner_text() for el in text_els if await el.inner_text()])
                        text = re.sub(r'\s+', ' ', text).strip()

                        if len(text) > 40:
                            temp_results.append({
                                "review_id": rid,
                                "rating": rating,
                                "text": text,
                                "author": "Google User",
                                "extracted_at": datetime.now(timezone.utc).isoformat(),
                            })
                    except:
                        continue

                if temp_results:
                    logger.info(f"Success on attempt {attempt}: {len(temp_results)} reviews")
                    results.extend(temp_results)
                    if len(results) >= limit:
                        break

            except Exception as e:
                logger.error(f"Attempt {attempt} failed: {e}", exc_info=True)
                # Save screenshot for debug (Railway /tmp)
                if page:
                    try:
                        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
                        await page.screenshot(path=f"/tmp/fail-attempt-{attempt}-{ts}.png", full_page=True)
                        logger.info(f"Screenshot saved: /tmp/fail-attempt-{attempt}-{ts}.png")
                    except:
                        pass

            finally:
                if page:
                    await page.close()
                if context:
                    await context.close()

            await asyncio.sleep(random.uniform(2, 5))  # Delay between attempts

        if not results:
            logger.warning("All attempts failed → no reviews collected")
        else:
            logger.info(f"Total collected: {len(results)} reviews")

        return results[:limit]


# Global singleton instance
scraper_instance = RobustScraper()

# FastAPI / callable entry
async def fetch_reviews(place_id: str, limit: int = 100) -> List[Dict[str, Any]]:
    try:
        return await scraper_instance.fetch_reviews(place_id, limit)
    except Exception as e:
        logger.critical(f"Fatal scraper error: {e}")
        return []
