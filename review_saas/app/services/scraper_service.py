# filename: app/services/scraper.py

from __future__ import annotations

import logging
import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional

from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)


class Scraper:
    """
    Google Maps Review Scraper

    Features
    --------
    • Unlimited scrolling
    • Date filtering
    • Async compatible
    • No external API required
    """

    def __init__(self):
        logger.info("✅ Playwright scraper initialized")

    async def fetch_reviews(
        self,
        place_url: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[Dict[str, Any]]:

        logger.info(f"🚀 Starting review scrape: {place_url}")

        start = datetime.fromisoformat(start_date) if start_date else None
        end = datetime.fromisoformat(end_date) if end_date else None

        reviews: List[Dict[str, Any]] = []

        async with async_playwright() as p:

            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            await page.goto(place_url)

            await asyncio.sleep(5)

            # Click Reviews button
            try:
                await page.locator('button[jsaction*="pane.reviewChart.moreReviews"]').click()
                await asyncio.sleep(3)
            except Exception:
                logger.warning("Reviews button not found")

            scroll_container = page.locator('div[role="feed"]')

            last_height = 0

            while True:

                await scroll_container.evaluate(
                    "(el) => el.scrollBy(0, 10000)"
                )

                await asyncio.sleep(2)

                current_height = await scroll_container.evaluate(
                    "(el) => el.scrollHeight"
                )

                if current_height == last_height:
                    break

                last_height = current_height

            review_cards = await page.locator('div[data-review-id]').all()

            logger.info(f"📊 Total review elements found: {len(review_cards)}")

            for card in review_cards:

                try:

                    author = await card.locator('.d4r55').inner_text()

                    rating = await card.locator('span[role="img"]').get_attribute(
                        "aria-label"
                    )

                    text = await card.locator('.wiI7pd').inner_text()

                    date_text = await card.locator('.rsqaWe').inner_text()

                    review_date = self._parse_date(date_text)

                    if start and review_date < start:
                        continue

                    if end and review_date > end:
                        continue

                    reviews.append(
                        {
                            "review_id": await card.get_attribute("data-review-id"),
                            "author": author,
                            "rating": self._parse_rating(rating),
                            "text": text,
                            "date": review_date.isoformat(),
                            "response": None,
                            "response_date": None,
                        }
                    )

                except Exception:
                    continue

            await browser.close()

        logger.info(f"✅ Reviews scraped after filtering: {len(reviews)}")

        return reviews

    def _parse_rating(self, rating_text: str) -> int:
        try:
            return int(rating_text.split(" ")[0])
        except Exception:
            return 0

    def _parse_date(self, date_text: str) -> datetime:
        """
        Convert Google relative dates to real datetime
        Example:
        '2 months ago'
        """

        now = datetime.utcnow()

        try:

            value = int(date_text.split()[0])

            if "day" in date_text:
                return now.replace(day=max(1, now.day - value))

            if "week" in date_text:
                return now.replace(day=max(1, now.day - (value * 7)))

            if "month" in date_text:
                return now.replace(month=max(1, now.month - value))

            if "year" in date_text:
                return now.replace(year=now.year - value)

        except Exception:
            pass

        return now
