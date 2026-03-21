# scraper.py

import asyncio
import random
import re
from typing import Optional, Dict

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from playwright_stealth import stealth_async

# Rotating User Agents (anti-detection)
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_5) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
]

async def _extract_rating_and_reviews(page) -> Optional[Dict]:
    """
    Try multiple strategies to extract rating and review count
    """

    # -------- Rating Extraction --------
    rating = None

    rating_patterns = [
        r"(\d\.\d)\s*out of 5",
        r"Rated\s*(\d\.\d)",
        r"(\d\.\d)\s*stars",
    ]

    possible_rating_selectors = [
        'span[aria-label*="Rated"]',
        'div[role="heading"] span',
        'span[jsname]',
    ]

    for selector in possible_rating_selectors:
        try:
            elements = await page.query_selector_all(selector)
            for el in elements:
                text = await el.inner_text()
                for pattern in rating_patterns:
                    match = re.search(pattern, text, re.IGNORECASE)
                    if match:
                        rating = float(match.group(1))
                        break
                if rating:
                    break
        except:
            continue
        if rating:
            break

    # -------- Review Count Extraction --------
    review_count = None

    review_patterns = [
        r"([\d,]+)\s*reviews",
        r"([\d,]+)\s*Ratings",
    ]

    possible_review_selectors = [
        'span:has-text("reviews")',
        'div:has-text("reviews")',
        'a:has-text("reviews")',
    ]

    for selector in possible_review_selectors:
        try:
            elements = await page.query_selector_all(selector)
            for el in elements:
                text = await el.inner_text()
                for pattern in review_patterns:
                    match = re.search(pattern, text, re.IGNORECASE)
                    if match:
                        review_count = int(match.group(1).replace(",", ""))
                        break
                if review_count:
                    break
        except:
            continue
        if review_count:
            break

    if rating and review_count:
        return {"rating": rating, "review_count": review_count}

    return None


async def fetch_google_reviews(query: str, retries: int = 3) -> Optional[Dict]:
    """
    MAIN FUNCTION — Use this in your project
    """

    for attempt in range(retries):
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)

                context = await browser.new_context(
                    user_agent=random.choice(USER_AGENTS),
                    viewport={"width": 1280, "height": 800},
                    locale="en-US",
                )

                page = await context.new_page()
                await stealth_async(page)

                # Google search URL
                url = f"https://www.google.com/search?q={query.replace(' ', '+')}"

                await page.goto(url, timeout=60000)

                # Random human-like delay
                await asyncio.sleep(random.uniform(2, 4))

                # Scroll slightly (human behavior)
                await page.mouse.wheel(0, random.randint(200, 600))
                await asyncio.sleep(random.uniform(1, 2))

                # Extract data
                result = await _extract_rating_and_reviews(page)

                await browser.close()

                if result:
                    return result

        except PlaywrightTimeoutError:
            print(f"⏳ Timeout on attempt {attempt+1}")
        except Exception as e:
            print(f"❌ Attempt {attempt+1} failed: {e}")

        # Retry delay
        await asyncio.sleep(random.uniform(2, 5))

    print("🚫 All attempts failed.")
    return {
        "rating": 0.0,
        "review_count": 0
    }


# Optional test run
if __name__ == "__main__":
    async def test():
        result = await fetch_google_reviews("Gloria Jeans DHA Lahore")
        print(result)

    asyncio.run(test())
