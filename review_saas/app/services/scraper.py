import logging
import asyncio
import random
from datetime import datetime, timezone
from typing import List, Dict, Any

import httpx
from playwright.async_api import async_playwright

# =====================================================
# 🔧 LOGGING
# =====================================================
logger = logging.getLogger("scraper")
logging.basicConfig(level=logging.INFO)

# =====================================================
# 🌍 PROXIES (ADD YOURS)
# =====================================================
PROXIES = [
    # "http://user:pass@host:port"
]

# =====================================================
# 🧠 USER AGENTS
# =====================================================
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8)",
]

# =====================================================
# ⚙️ CONFIG
# =====================================================
MAX_CONCURRENT_BROWSERS = 3
MAX_CONCURRENT_TASKS = 5
SCROLL_LIMIT = 25


# =====================================================
# 🧩 UTILS
# =====================================================
def get_proxy():
    return random.choice(PROXIES) if PROXIES else None


def get_user_agent():
    return random.choice(USER_AGENTS)


def clean(text: str) -> str:
    return " ".join(text.split()) if text else ""


# =====================================================
# 🕵️ STEALTH ENGINE
# =====================================================
class ProductionScraper:

    def __init__(self):
        self.browser = None
        self.playwright = None
        self.semaphore = asyncio.Semaphore(MAX_CONCURRENT_TASKS)

    # ===============================
    # 🚀 INIT BROWSER (REUSE)
    # ===============================
    async def init_browser(self):
        if self.browser:
            return

        self.playwright = await async_playwright().start()

        self.browser = await self.playwright.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--disable-infobars"
            ]
        )

        logger.info("🔥 Browser initialized (REUSED)")

    # ===============================
    # 🧠 CREATE STEALTH PAGE
    # ===============================
    async def create_page(self):

        proxy = get_proxy()
        ua = get_user_agent()

        context = await self.browser.new_context(
            user_agent=ua,
            locale="en-US",
            viewport={"width": 1280, "height": 800},
        )

        page = await context.new_page()

        # 🔥 FULL STEALTH
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'languages', { get: () => ['en-US','en'] });
            Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3,4,5] });
            window.chrome = { runtime: {} };
        """)

        return page, proxy, ua

    # ===============================
    # 🎯 SINGLE SCRAPE ATTEMPT
    # ===============================
    async def scrape_once(self, place_id: str, attempt_id: int):

        async with self.semaphore:

            page, proxy, ua = await self.create_page()

            label = f"ATTEMPT_{attempt_id}"

            try:
                logger.info(f"🚀 {label} started")

                url = f"https://www.google.com/maps/place/?q=place_id:{place_id}"
                await page.goto(url, timeout=60000)

                await asyncio.sleep(random.uniform(2, 4))

                # Accept cookies
                try:
                    buttons = await page.query_selector_all("button")
                    for b in buttons:
                        txt = await b.inner_text()
                        if "accept" in txt.lower():
                            await b.click()
                except:
                    pass

                # Open reviews
                selectors = [
                    'button[jsaction*="pane.reviewChart.moreReviews"]',
                    'button:has-text("reviews")',
                    'button:has-text("Review")'
                ]

                opened = False
                for sel in selectors:
                    try:
                        await page.click(sel, timeout=3000)
                        opened = True
                        break
                    except:
                        continue

                if not opened:
                    await page.close()
                    return []

                await asyncio.sleep(3)

                # Scroll
                for _ in range(SCROLL_LIMIT):
                    await page.mouse.wheel(0, random.randint(3000, 6000))
                    await asyncio.sleep(random.uniform(0.8, 1.8))

                # Extract
                cards = await page.query_selector_all('div[data-review-id]')
                results = []

                for c in cards:
                    try:
                        rid = await c.get_attribute("data-review-id")

                        rating_el = await c.query_selector('span[aria-label*="stars"]')
                        rating = int((await rating_el.get_attribute("aria-label"))[0]) if rating_el else 5

                        text_el = await c.query_selector('span[jsname="fbQN7e"]') or \
                                  await c.query_selector('span[jsname="bN97Pc"]')

                        text = await text_el.inner_text() if text_el else ""

                        if text:
                            results.append({
                                "review_id": rid,
                                "rating": rating,
                                "text": clean(text),
                                "method": label,
                                "proxy": proxy,
                                "user_agent": ua,
                                "extracted_at": datetime.now(timezone.utc).isoformat()
                            })
                    except:
                        continue

                await page.close()

                if results:
                    logger.info(f"✅ SUCCESS {label}: {len(results)}")
                else:
                    logger.warning(f"❌ FAILED {label}")

                return results

            except Exception as e:
                logger.error(f"⚠️ ERROR {label}: {e}")
                await page.close()
                return []

    # ===============================
    # 🔁 MAIN RUNNER (PARALLEL)
    # ===============================
    async def run(self, place_id: str, limit=100):

        await self.init_browser()

        tasks = [
            self.scrape_once(place_id, i)
            for i in range(1, 16)  # 15 parallel attempts
        ]

        results = await asyncio.gather(*tasks)

        # Flatten results
        all_reviews = [item for sublist in results for item in sublist]

        if all_reviews:
            logger.info(f"🎯 FINAL SUCCESS: {len(all_reviews)} reviews")
            return all_reviews[:limit]

        logger.error("💀 ALL ATTEMPTS FAILED")
        return []

    # ===============================
    # 🧹 CLEANUP
    # ===============================
    async def close(self):
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()


# =====================================================
# 🔗 FASTAPI ENTRY
# =====================================================
async def fetch_reviews(place_id: str, limit: int = 100):
    scraper = ProductionScraper()

    try:
        return await scraper.run(place_id, limit)
    finally:
        await scraper.close()
