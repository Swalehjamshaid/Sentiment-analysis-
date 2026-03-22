import logging
import asyncio
from datetime import datetime, timezone
from typing import List, Dict, Any

from tenacity import retry, stop_after_attempt, wait_exponential
from playwright.async_api import async_playwright, Page

logger = logging.getLogger("scraper")


class GoogleMapsScraper:
    def __init__(self, desktop_mode: bool = False):
        self.max_scroll = 30
        self.scroll_pause = 2
        self.desktop_mode = desktop_mode

    def _clean_text(self, text: str) -> str:
        if not text:
            return ""
        return " ".join(text.split()).strip()

    async def _auto_scroll(self, page: Page):
        last_height = 0
        for i in range(self.max_scroll):
            await page.mouse.wheel(0, 5000)
            await asyncio.sleep(self.scroll_pause)
            new_height = await page.evaluate("document.body.scrollHeight")
            if new_height == last_height:
                logger.info("⛔ No more new reviews loaded (scroll stop)")
                break
            last_height = new_height
            logger.info(f"🔄 Scrolling... ({i+1})")

    async def _close_popups(self, page: Page):
        """Closes any interfering dialogs."""
        popups = await page.query_selector_all('div[role="dialog"] button')
        for btn in popups:
            try:
                await btn.click()
                logger.info("✅ Closed a popup/modal")
            except:
                continue

    async def _open_reviews_panel(self, page: Page):
        """Tries multiple selectors to open reviews panel."""
        try:
            # Primary button
            await page.wait_for_selector('button[jsaction*="pane.reviewChart.moreReviews"]', timeout=8000)
            await page.click('button[jsaction*="pane.reviewChart.moreReviews"]')
            logger.info("✅ Opened reviews panel (primary)")
            return True
        except:
            # Fallback: any button containing 'review'
            try:
                btns = await page.query_selector_all('button')
                for btn in btns:
                    text = await btn.inner_text()
                    if "review" in text.lower():
                        await btn.click()
                        logger.info("✅ Opened reviews panel (fallback)")
                        return True
            except:
                pass
        return False

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=3, max=10))
    async def run(self, place_id: str, limit: int = 200) -> List[Dict[str, Any]]:
        all_reviews = []

        logger.info(f"🚀 Starting scraper for place_id: {place_id}")

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-blink-features=AutomationControlled"]
            )

            user_agent = (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                if self.desktop_mode
                else "Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) AppleWebKit/537.36 "
                     "(KHTML, like Gecko) Chrome/122.0.6261.105 Mobile Safari/537.36"
            )

            context = await browser.new_context(user_agent=user_agent, locale="en-US")
            page = await context.new_page()

            url = f"https://www.google.com/maps/place/?q=place_id:{place_id}"
            await page.goto(url, timeout=60000)
            await page.wait_for_timeout(5000)

            # Close popups if any
            await self._close_popups(page)

            # Open reviews panel
            if not await self._open_reviews_panel(page):
                logger.error("❌ Could not open reviews panel")
                await browser.close()
                return []

            await page.wait_for_timeout(3000)

            # Optional: sort by newest
            try:
                await page.click('button[aria-label*="Sort"]')
                await page.wait_for_timeout(1000)
                await page.click('div[role="menuitemradio"] >> nth=1')
                logger.info("✅ Sorted by newest")
            except:
                logger.warning("⚠️ Sorting not available")

            # Scroll to load reviews
            await self._auto_scroll(page)

            # Extract reviews
            review_cards = await page.query_selector_all('div[data-review-id]')
            for card in review_cards:
                if len(all_reviews) >= limit:
                    break
                try:
                    review_id = await card.get_attribute("data-review-id")

                    # rating
                    rating_el = await card.query_selector('span[aria-label*="stars"]')
                    rating = 5
                    if rating_el:
                        rating_text = await rating_el.get_attribute("aria-label")
                        rating = int(rating_text[0])

                    # text
                    text_el = await card.query_selector('span[jsname="fbQN7e"]')
                    if not text_el:
                        text_el = await card.query_selector('span[jsname="bN97Pc"]')
                    text = await text_el.inner_text() if text_el else ""

                    # author
                    author_el = await card.query_selector('.d4r55')
                    author = await author_el.inner_text() if author_el else "Google User"

                    # review time
                    time_el = await card.query_selector('span.rsqaWe')
                    review_time = await time_el.inner_text() if time_el else ""

                    clean_body = self._clean_text(text)
                    if len(clean_body) > 5:
                        all_reviews.append({
                            "review_id": review_id,
                            "rating": rating,
                            "text": clean_body,
                            "author": author,
                            "review_time": review_time,
                            "extracted_at": datetime.now(timezone.utc).isoformat()
                        })
                except Exception as e:
                    logger.warning(f"⚠️ Parsing error: {e}")
                    continue

            await browser.close()

        logger.info(f"✅ Scraping complete: {len(all_reviews)} reviews collected")
        return all_reviews


# FastAPI Integration
async def fetch_reviews(place_id: str, limit: int = 200, desktop_mode: bool = False):
    scraper = GoogleMapsScraper(desktop_mode=desktop_mode)
    return await scraper.run(place_id=place_id, limit=limit)
