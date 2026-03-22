# scraper.py
# Updated: March 22, 2026 – Optimized for Playwright 1.58+, stealth, tenacity retries
# Compatible with your full requirements stack (playwright-stealth, fake-useragent, tenacity, etc.)
# Usage: await fetch_reviews("https://www.google.com/maps/place/...")

import asyncio
import logging
import random
import re
from datetime import datetime, timezone
from typing import List, Dict, Any

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from playwright_stealth import stealth_async
from fake_useragent import UserAgent
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger("scraper")


@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1.2, min=4, max=20),
    retry=retry_if_exception_type((PlaywrightTimeoutError, Exception)),
    before_sleep=lambda retry_state: logger.info(f"Retrying... attempt {retry_state.attempt_number}")
)
async def fetch_reviews(
    place_url: str,
    limit: int = 100,
    sort_by_newest: bool = True,
    headless: bool = True,
) -> List[Dict[str, Any]]:
    """
    Asynchronously fetch Google Maps reviews using Playwright + stealth.
    Returns list of dicts matching your original format.
    """
    all_reviews: List[Dict[str, Any]] = []
    ua = UserAgent()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"]
        )
        context = await browser.new_context(
            user_agent=ua.random,
            viewport={"width": 1366, "height": 768},
            locale="en-US",
            timezone_id="Asia/Karachi",
            # Optional: proxy={"server": "http://your-residential-proxy:port"}  # add when scaling
            bypass_csp=True,
        )
        page = await context.new_page()
        await stealth_async(page)  # Apply stealth patches

        try:
            logger.info(f"🌐 Navigating to: {place_url}")
            await page.goto(place_url, wait_until="networkidle", timeout=60000)

            # Handle consent / cookie banner (common in PK region)
            try:
                await page.get_by_role("button", name=re.compile(r"Accept all|Agree|Accept|OK|同意|قبول", re.I)).click(timeout=10000)
                logger.debug("Consent banner accepted")
            except:
                pass

            # Switch to Reviews tab if not already there
            try:
                reviews_tab = page.get_by_role("tab", name=re.compile(r"Reviews|مراجعات|評価|評論", re.I))
                if await reviews_tab.is_visible(timeout=12000):
                    await reviews_tab.click()
                    await asyncio.sleep(random.uniform(2.0, 3.5))
            except Exception as e:
                logger.debug(f"Reviews tab handling: {e}")

            # Sort by newest if requested (helps load recent + more content)
            if sort_by_newest:
                try:
                    sort_btn = page.get_by_role("button", name=re.compile(r"Sort|Newest|Most recent|最新|أحدث", re.I))
                    if await sort_btn.is_visible(timeout=8000):
                        await sort_btn.click()
                        await page.get_by_role("menuitem", name=re.compile(r"Newest|Most recent|أحدث|最新順", re.I)).click()
                        await asyncio.sleep(random.uniform(2.5, 4.0))
                except:
                    pass

            # Scroll reviews container to load more
            scroll_container_sel = (
                "div[role='feed'], "
                "div[role='main'] div[aria-label*='reviews'], "
                "[jsaction*='pane.review'], "
                ".m6QErb[aria-label*='Reviews']"
            )
            last_loaded = 0
            max_scroll_attempts = 40

            for attempt in range(max_scroll_attempts):
                review_elements = await page.query_selector_all('[data-review-id]')
                current_loaded = len(review_elements)

                if current_loaded >= limit or current_loaded <= last_loaded:
                    break

                last_loaded = current_loaded
                logger.debug(f"Loaded {current_loaded} reviews so far... scrolling")

                await page.evaluate(
                    f"""
                    () => {{
                        const container = document.querySelector('{scroll_container_sel}') ||
                                          document.querySelector('div[role="main"]') ||
                                          document.body;
                        if (container) container.scrollTop = container.scrollHeight;
                    }}
                    """
                )
                await asyncio.sleep(random.uniform(2.3, 5.1))  # human-like variance

            # Parse loaded reviews
            review_elements = await page.query_selector_all('[data-review-id]')
            logger.info(f"🔍 Parsing {len(review_elements)} review elements (limit: {limit})")

            for el in review_elements[:limit]:
                try:
                    review_id = await el.get_attribute("data-review-id")
                    if not review_id:
                        review_id = f"fallback_{random.randint(100000, 999999)}"

                    # Rating via aria-label (very stable)
                    star_el = await el.query_selector(
                        '[role="img"][aria-label*="star"], [aria-label*="stars"], .lTi8oc span'
                    )
                    rating = None
                    if star_el:
                        aria = await star_el.get_attribute("aria-label") or ""
                        match = re.search(r"(\d[\d.]*)", aria)
                        if match:
                            rating = int(float(match.group(1)))

                    # Review text – broad fallback selectors (2025–2026 stable)
                    text_selectors = [
                        'span[jsname]', 'div[jsname]', '.MyEned', '.fontBodyMedium',
                        '.jftiEf .wiI7pd', 'div[style*="font-size"] span'
                    ]
                    text_parts = []
                    for sel in text_selectors:
                        els = await el.query_selector_all(sel)
                        for t_el in els:
                            txt = (await t_el.inner_text()).strip()
                            if txt and len(txt) > 12 and "google" not in txt.lower() and "translate" not in txt.lower():
                                text_parts.append(txt)

                    clean_text = re.sub(r'\s+', ' ', " ".join(text_parts)).strip()
                    if len(clean_text) < 20:
                        continue

                    # Author
                    author_el = await el.query_selector(
                        '.d4r55, .TSUbDb, span[style*="font-weight"], .fontHeadlineSmall'
                    )
                    author = (await author_el.inner_text()).strip() if author_el else "Google User"

                    all_reviews.append({
                        "review_id": review_id,
                        "rating": rating if rating is not None else 0,
                        "text": clean_text,
                        "author": author,
                        "extracted_at": datetime.now(timezone.utc).isoformat(),
                    })

                except Exception as parse_err:
                    logger.debug(f"Single review parse error: {parse_err}")
                    continue

        except Exception as critical_err:
            logger.error(f"Critical scrape failure for {place_url}: {critical_err}", exc_info=True)
        finally:
            await context.close()
            await browser.close()

    logger.info(f"✅ Completed: {len(all_reviews)} reviews extracted from {place_url}")
    return all_reviews


# Quick sync test runner (for development)
def test_scraper():
    logging.basicConfig(level=logging.INFO)
    # Replace with a real Maps place URL (Share → Copy link)
    test_url = "https://www.google.com/maps/place/Lahore+Fort/@31.5883,74.3105,17z/data=..."
    reviews = asyncio.run(fetch_reviews(test_url, limit=60, headless=True))
    for r in reviews[:3]:
        print(r)
    print(f"Total extracted: {len(reviews)}")


if __name__ == "__main__":
    test_scraper()
