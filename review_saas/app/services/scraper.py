import logging
import asyncio
import random
import re
from datetime import datetime, timezone
from typing import List, Dict, Any

import httpx
from playwright.async_api import async_playwright

logger = logging.getLogger("scraper")

# =====================================================
# 🌍 ADD YOUR PROXIES HERE
# =====================================================
PROXIES = [
    # "http://user:pass@host:port"
]


class MultiStrategyScraper:

    def __init__(self):
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Mozilla/5.0 (Linux; Android 14; Pixel 8)",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
        ]

    def clean(self, text: str) -> str:
        return " ".join(text.split()) if text else ""

    def get_proxy(self):
        if PROXIES:
            proxy = random.choice(PROXIES)
            logger.info(f"🌍 Using Proxy: {proxy}")
            return proxy
        return None

    # =====================================================
    # 🔥 PLAYWRIGHT CORE METHOD (WITH PROXY)
    # =====================================================
    async def playwright_attempt(self, place_id, config):

        label = config["label"]
        proxy = self.get_proxy()

        logger.info(f"🚀 Running {label}")

        try:
            async with async_playwright() as p:

                browser = await p.chromium.launch(
                    headless=True,
                    proxy={"server": proxy} if proxy else None,
                    args=["--no-sandbox", "--disable-blink-features=AutomationControlled"]
                )

                context = await browser.new_context(
                    user_agent=random.choice(self.user_agents),
                    viewport={"width": 1280, "height": 800}
                )

                page = await context.new_page()

                # Hide automation
                await page.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                """)

                url = f"https://www.google.com/maps/place/?q=place_id:{place_id}"
                await page.goto(url, timeout=60000)

                await asyncio.sleep(config["wait"])

                # Accept cookies
                if config["popup"]:
                    try:
                        buttons = await page.query_selector_all("button")
                        for b in buttons:
                            txt = await b.inner_text()
                            if "accept" in txt.lower():
                                await b.click()
                    except:
                        pass

                # Open reviews
                opened = False
                for sel in config["selectors"]:
                    try:
                        await page.click(sel, timeout=3000)
                        opened = True
                        break
                    except:
                        continue

                if not opened:
                    await browser.close()
                    return []

                await asyncio.sleep(3)

                # Scroll
                for _ in range(config["scroll"]):
                    await page.mouse.wheel(0, 5000)
                    await asyncio.sleep(config["sleep"])

                # Expand
                try:
                    more_buttons = await page.query_selector_all('button[jsname="gxjVle"]')
                    for m in more_buttons:
                        await m.click()
                except:
                    pass

                # Extract
                cards = await page.query_selector_all('div[data-review-id]')
                results = []

                for c in cards:
                    try:
                        rid = await c.get_attribute("data-review-id")

                        rating_el = await c.query_selector('span[aria-label*="stars"]')
                        rating = 5
                        if rating_el:
                            txt = await rating_el.get_attribute("aria-label")
                            rating = int(txt[0]) if txt else 5

                        text_el = await c.query_selector('span[jsname="fbQN7e"]') or \
                                  await c.query_selector('span[jsname="bN97Pc"]')

                        text = await text_el.inner_text() if text_el else ""

                        if text:
                            results.append({
                                "review_id": rid,
                                "rating": rating,
                                "text": self.clean(text),
                                "method": label,
                                "proxy": proxy,
                                "extracted_at": datetime.now(timezone.utc).isoformat()
                            })
                    except:
                        continue

                await browser.close()

                return results

        except Exception as e:
            logger.error(f"⚠️ ERROR {label}: {e}")
            return []

    # =====================================================
    # 🌐 HTTP METHOD (WITH PROXY)
    # =====================================================
    async def http_attempt(self, place_id, label, url):

        proxy = self.get_proxy()

        logger.info(f"🌐 Running {label}")

        try:
            async with httpx.AsyncClient(
                timeout=20,
                proxies=proxy
            ) as client:

                r = await client.get(url)

            html = r.text

            matches = re.findall(r'aria-label="(\d\.\d) stars".*?<span>(.*?)</span>', html, re.DOTALL)

            results = []

            for i, (rating, text) in enumerate(matches):
                results.append({
                    "review_id": f"{label}_{i}",
                    "rating": float(rating),
                    "text": self.clean(text),
                    "method": label,
                    "proxy": proxy,
                    "extracted_at": datetime.now(timezone.utc).isoformat()
                })

            return results

        except:
            return []

    # =====================================================
    # 🔁 MAIN RUNNER (30 STRATEGIES WITH PROXY ROTATION)
    # =====================================================
    async def run(self, place_id: str, limit=100):

        selectors = [
            'button[jsaction*="pane.reviewChart.moreReviews"]',
            'button:has-text("reviews")',
            'button:has-text("Review")'
        ]

        # 🔥 20 Playwright Strategies
        for i in range(20):
            config = {
                "label": f"PW_{i+1}",
                "wait": 3 + (i % 3),
                "popup": i % 2 == 0,
                "scroll": 15 + (i * 2),
                "sleep": 1 + (i % 2),
                "selectors": selectors[::-1] if i % 2 else selectors
            }

            res = await self.playwright_attempt(place_id, config)

            if res:
                return res[:limit]

        # 🌐 10 HTTP Strategies
        urls = [
            f"https://www.google.com/search?q=reviews+{place_id}",
            f"https://www.google.com/search?q={place_id}+rating",
            f"https://www.google.com/search?q={place_id}+feedback",
            f"https://www.google.com/search?q={place_id}+opinions",
            f"https://www.google.com/search?q={place_id}+stars",
            f"https://www.google.com/search?q={place_id}+experience",
            f"https://www.google.com/search?q={place_id}+customer+reviews",
            f"https://www.google.com/search?q=google+reviews+{place_id}",
            f"https://www.google.com/maps/place/?q=place_id:{place_id}",
            f"https://www.google.com/search?q={place_id}+review+site",
        ]

        for i, url in enumerate(urls):
            res = await self.http_attempt(place_id, f"HTTP_{i+1}", url)

            if res:
                return res[:limit]

        logger.error("💀 ALL STRATEGIES FAILED")
        return []


# =====================================================
# 🔗 FASTAPI ENTRY
# =====================================================
async def fetch_reviews(place_id: str, limit: int = 100):
    scraper = MultiStrategyScraper()
    return await scraper.run(place_id, limit)
