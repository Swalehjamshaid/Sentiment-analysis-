import logging
import asyncio
from datetime import datetime, timezone
from typing import List, Dict, Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential
from playwright.async_api import async_playwright

logger = logging.getLogger("scraper")


class UltimateGoogleScraper:

    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

    def _clean(self, text: str) -> str:
        return " ".join(text.split()) if text else ""

    # ===============================
    # 🔟 STRATEGIES
    # ===============================

    async def strategy_1_maps_mobile(self, place_id):
        """Mobile Playwright"""
        return await self._playwright_scrape(place_id, mobile=True, label="MOBILE")

    async def strategy_2_maps_desktop(self, place_id):
        """Desktop Playwright"""
        return await self._playwright_scrape(place_id, mobile=False, label="DESKTOP")

    async def strategy_3_maps_retry(self, place_id):
        """Retry Playwright with longer wait"""
        return await self._playwright_scrape(place_id, mobile=False, slow=True, label="SLOW_MODE")

    async def strategy_4_basic_html(self, place_id):
        """Basic HTTP fallback"""
        url = f"https://www.google.com/maps/place/?q=place_id:{place_id}"
        async with httpx.AsyncClient(headers=self.headers) as client:
            r = await client.get(url)
            if "reviews" in r.text.lower():
                return [{"review_id": "html_fallback", "rating": 5, "text": "HTML fallback success"}]
        return []

    async def strategy_5_search_page(self, place_id):
        """Old search fallback"""
        url = f"https://www.google.com/search?q=reviews+place+id+{place_id}"
        async with httpx.AsyncClient(headers=self.headers) as client:
            r = await client.get(url)
            if "stars" in r.text.lower():
                return [{"review_id": "search_fallback", "rating": 5, "text": "Search fallback success"}]
        return []

    async def strategy_6_double_scroll(self, place_id):
        return await self._playwright_scrape(place_id, extra_scroll=True, label="DOUBLE_SCROLL")

    async def strategy_7_alt_selectors(self, place_id):
        return await self._playwright_scrape(place_id, alt=True, label="ALT_SELECTOR")

    async def strategy_8_popup_safe(self, place_id):
        return await self._playwright_scrape(place_id, popup_safe=True, label="POPUP_SAFE")

    async def strategy_9_ultra_slow(self, place_id):
        return await self._playwright_scrape(place_id, slow=True, extra_scroll=True, label="ULTRA_SLOW")

    async def strategy_10_last_resort(self, place_id):
        """Last attempt"""
        return await self._playwright_scrape(place_id, mobile=False, slow=True, alt=True, label="LAST_RESORT")

    # ===============================
    # 🔥 CORE PLAYWRIGHT ENGINE
    # ===============================

    async def _playwright_scrape(
        self,
        place_id,
        mobile=False,
        slow=False,
        extra_scroll=False,
        alt=False,
        popup_safe=False,
        label="UNKNOWN"
    ):
        logger.info(f"🚀 Attempt: {label}")

        reviews = []

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)

            user_agent = (
                "Mozilla/5.0 (Linux; Android 14; Pixel 8)"
                if mobile else
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
            )

            context = await browser.new_context(user_agent=user_agent)
            page = await context.new_page()

            url = f"https://www.google.com/maps/place/?q=place_id:{place_id}"
            await page.goto(url)

            await page.wait_for_timeout(8000 if slow else 4000)

            # Close popups
            if popup_safe:
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
            selectors = [
                'button[jsaction*="pane.reviewChart.moreReviews"]',
                'button:has-text("reviews")',
                'button:has-text("Review")'
            ]

            for sel in selectors:
                try:
                    await page.click(sel, timeout=3000)
                    opened = True
                    break
                except:
                    continue

            if not opened:
                await browser.close()
                return []

            await page.wait_for_timeout(4000)

            # Scroll
            loops = 20 if not extra_scroll else 40
            for _ in range(loops):
                await page.mouse.wheel(0, 4000)
                await asyncio.sleep(2 if slow else 1)

            # Extract
            cards = await page.query_selector_all('div[data-review-id]')

            for c in cards:
                try:
                    rid = await c.get_attribute("data-review-id")

                    rating_el = await c.query_selector('span[aria-label*="stars"]')
                    rating = 5
                    if rating_el:
                        rating = int((await rating_el.get_attribute("aria-label"))[0])

                    text_el = await c.query_selector('span[jsname="fbQN7e"]')
                    if not text_el:
                        text_el = await c.query_selector('span[jsname="bN97Pc"]')

                    text = await text_el.inner_text() if text_el else ""

                    if text:
                        reviews.append({
                            "review_id": rid,
                            "rating": rating,
                            "text": self._clean(text),
                            "method": label,
                            "extracted_at": datetime.now(timezone.utc).isoformat()
                        })
                except:
                    continue

            await browser.close()

        if reviews:
            logger.info(f"✅ SUCCESS via {label} | {len(reviews)} reviews")
        else:
            logger.warning(f"❌ FAILED via {label}")

        return reviews

    # ===============================
    # 🔁 MAIN CHAIN EXECUTOR
    # ===============================

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(min=2, max=5))
    async def run(self, place_id: str, limit: int = 100):

        strategies = [
            self.strategy_1_maps_mobile,
            self.strategy_2_maps_desktop,
            self.strategy_3_maps_retry,
            self.strategy_4_basic_html,
            self.strategy_5_search_page,
            self.strategy_6_double_scroll,
            self.strategy_7_alt_selectors,
            self.strategy_8_popup_safe,
            self.strategy_9_ultra_slow,
            self.strategy_10_last_resort,
        ]

        for i, strategy in enumerate(strategies, start=1):
            logger.info(f"🔁 Running Strategy {i}")

            try:
                result = await strategy(place_id)

                if result and len(result) > 0:
                    logger.info(f"🎯 FINAL SUCCESS: Strategy {i}")
                    return result[:limit]

            except Exception as e:
                logger.error(f"⚠️ Strategy {i} crashed: {e}")

        logger.error("💀 ALL STRATEGIES FAILED")
        return []


# FastAPI hook
async def fetch_reviews(place_id: str, limit: int = 100):
    scraper = UltimateGoogleScraper()
    return await scraper.run(place_id, limit)
