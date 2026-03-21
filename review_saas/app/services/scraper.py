# scraper.py (FINAL FIXED VERSION)

import asyncio
import random
import re
from typing import List, Dict

from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_5) AppleWebKit/537.36 Chrome/119 Safari/537.36",
]


async def fetch_reviews(query: str) -> List[Dict]:
    """
    This replaces broken Google API scraping
    Returns list of reviews (compatible with your system)
    """

    print(f"🚀 Starting REAL scraper for: {query}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        context = await browser.new_context(
            user_agent=random.choice(USER_AGENTS)
        )

        page = await context.new_page()
        await stealth_async(page)

        # Step 1: Open Google search
        await page.goto(f"https://www.google.com/search?q={query.replace(' ', '+')}", timeout=60000)

        await asyncio.sleep(3)

        # Step 2: Click on Reviews button
        try:
            await page.click('button:has-text("Reviews")', timeout=5000)
        except:
            try:
                await page.click('span:has-text("reviews")', timeout=5000)
            except:
                print("❌ Reviews button not found")
                await browser.close()
                return []

        await asyncio.sleep(3)

        # Step 3: Scroll to load reviews
        for _ in range(5):
            await page.mouse.wheel(0, 2000)
            await asyncio.sleep(2)

        # Step 4: Extract reviews
        review_blocks = await page.query_selector_all('div[data-review-id]')

        results = []

        for block in review_blocks:
            try:
                text_el = await block.query_selector('span[jsname]')
                rating_el = await block.query_selector('span[aria-label*="stars"]')

                text = await text_el.inner_text() if text_el else ""
                rating_text = await rating_el.get_attribute("aria-label") if rating_el else ""

                rating_match = re.search(r"(\d)", rating_text)
                rating = int(rating_match.group(1)) if rating_match else 0

                if text:
                    results.append({
                        "review_text": text,
                        "rating": rating
                    })

            except:
                continue

        await browser.close()

        print(f"✅ Scraped {len(results)} reviews")

        return results
