import asyncio
import logging
import random
import re
from datetime import datetime, timezone
from typing import List, Dict, Any

from playwright.async_api import async_playwright
from playwright_stealth import stealth_async
from fake_useragent import UserAgent
from tenacity import retry, stop_after_attempt, wait_exponential
import googlemaps

logger = logging.getLogger("scraper")

# ────────────────────────────────────────────────
#  SETTINGS  –  CHANGE THESE
# ────────────────────────────────────────────────
PROXY_LIST = [
    # "http://user:pass@residential-ip:port",
    # "http://user:pass@residential-ip:port",
    # add real residential proxies !!!
]

GOOGLE_API_KEY = "AIzaSyXXXXXXXXXXXXXXXXXXXXXXXXXXXX"  # ← real key or ""

MAX_ATTEMPTS = 6
TIMEOUT = 75000

# ────────────────────────────────────────────────
#  SCRAPER CLASS
# ────────────────────────────────────────────────
class HighSuccessScraper:
    def __init__(self):
        self.browser = None
        self.playwright = None
        self.ua = UserAgent()

    async def start_browser(self):
        if self.browser:
            return

        self.playwright = await async_playwright().start()
        proxy = random.choice(PROXY_LIST) if PROXY_LIST else None

        self.browser = await self.playwright.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-software-rasterizer",
                "--disable-blink-features=AutomationControlled",
            ],
            proxy={"server": proxy} if proxy else None
        )

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=3, max=15))
    async def _create_page(self):
        await self.start_browser()

        context = await self.browser.new_context(
            user_agent=self.ua.random,
            viewport={"width": 1366, "height": 768},
            locale="en-US",
            timezone_id="Asia/Karachi",
            bypass_csp=True,
            java_script_enabled=True,
        )

        page = await context.new_page()
        await stealth_async(page)

        # Extra stealth
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            window.chrome = { runtime: {} };
            Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
            Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => 8});
        """)

        return page, context

    async def scrape(self, place_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        page = None
        context = None
        results = []

        for attempt in range(1, MAX_ATTEMPTS + 1):
            logger.info(f"Attempt {attempt}/{MAX_ATTEMPTS} – place_id {place_id}")

            try:
                page, context = await self._create_page()

                # Different URLs to try
                urls = [
                    f"https://www.google.com/maps/place/_/data=!4m2!3m1!1s{place_id}",
                    f"https://www.google.com/maps/contrib/{place_id}/reviews",
                    f"https://www.google.com/maps/search/?api=1&query=place_id:{place_id}",
                ]

                url = random.choice(urls)
                await page.goto(url, wait_until="commit", timeout=TIMEOUT)
                await asyncio.sleep(random.uniform(2.2, 4.8))

                # Consent handling
                for btn_text in ["Accept all", "Accept", "Agree", "OK", "قبول"]:
                    try:
                        await page.get_by_role("button", name=re.compile(btn_text, re.I)).click(timeout=8000)
                        break
                    except:
                        pass

                # Try to open Reviews tab – many selectors
                review_buttons = [
                    '[aria-label*="Reviews"]',
                    'button:has-text("Reviews")',
                    'button:has-text("All reviews")',
                    'button[jsaction*="pane.review"]',
                    '[role="tab"] [aria-label*="Reviews"]',
                    'a:has-text("Reviews")',
                ]

                for sel in review_buttons:
                    try:
                        btn = page.locator(sel).first
                        if await btn.is_visible(timeout=7000):
                            await btn.hover()
                            await asyncio.sleep(0.6)
                            await btn.click(timeout=10000)
                            logger.info(f"Clicked: {sel}")
                            await asyncio.sleep(random.uniform(3.0, 6.0))
                            break
                    except:
                        pass

                # Wait for any review content
                try:
                    await page.wait_for_selector(
                        'div[data-review-id], .jftiEf, [role="feed"], span[jsname="bN97Pc"]',
                        timeout=20000
                    )
                except:
                    logger.warning("No review elements detected after wait")

                # Human-like scroll
                for _ in range(18):
                    await page.evaluate("window.scrollBy(0, window.innerHeight * 1.8)")
                    await asyncio.sleep(random.uniform(1.1, 2.9))

                # Extract
                cards = await page.query_selector_all('div[data-review-id], .jftiEf, div[jsaction*="review"]')
                logger.info(f"Found {len(cards)} cards")

                for card in cards:
                    try:
                        rid = await card.get_attribute("data-review-id") or f"gen_{random.randint(100000,999999)}"

                        # Rating
                        rating_el = await card.query_selector('[aria-label*="star"]')
                        rating = 5
                        if rating_el:
                            aria = await rating_el.get_attribute("aria-label") or ""
                            m = re.search(r"(\d+)", aria)
                            if m:
                                rating = int(m.group(1))

                        # Text
                        text_parts = []
                        for sel in ['span[jsname="bN97Pc"]', '.wiI7pd', '.MyEned', 'span[dir="auto"]']:
                            els = await card.query_selector_all(sel)
                            for el in els:
                                t = await el.inner_text()
                                if t and len(t.strip()) > 20:
                                    text_parts.append(t.strip())

                        text = " ".join(text_parts).strip()

                        if len(text) > 60:
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

            except Exception as e:
                logger.error(f"Attempt {attempt} failed: {e}", exc_info=True)
                if page:
                    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
                    await page.screenshot(path=f"/tmp/fail-{attempt}-{ts}.png", full_page=True)
                    html = await page.content()
                    with open(f"/tmp/fail-html-{attempt}-{ts}.html", "w", encoding="utf-8") as f:
                        f.write(html)
                    logger.info(f"Debug saved: /tmp/fail-*-{ts}.*")

            finally:
                if page:
                    await page.close()
                if context:
                    await context.close()

            await asyncio.sleep(random.uniform(3, 8))

        # FINAL FALLBACK: official API
        if not results and GOOGLE_API_KEY and GOOGLE_API_KEY != "AIzaSy...":
            try:
                gmaps = googlemaps.Client(key=GOOGLE_API_KEY)
                place = gmaps.place(place_id=place_id, fields=["reviews"])
                api_reviews = place.get("result", {}).get("reviews", [])
                logger.info(f"API fallback → {len(api_reviews)} reviews")
                results.extend([{
                    "review_id": str(r.get("time", "")),
                    "rating": r.get("rating", 0),
                    "text": r.get("text", ""),
                    "author": r.get("author_name", "Google User"),
                    "extracted_at": datetime.now(timezone.utc).isoformat(),
                } for r in api_reviews])
            except Exception as e:
                logger.error(f"API fallback failed: {e}")

        return results[:limit]


# Singleton
scraper = HighSuccessScraper()

async def fetch_reviews(place_id: str, limit: int = 100) -> List[Dict[str, Any]]:
    return await scraper.scrape(place_id, limit)
