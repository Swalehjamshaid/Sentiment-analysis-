# app/services/scraper.py
# Updated: March 22, 2026 – Compatible with playwright-stealth 2.0.2+
# Uses Stealth context manager instead of removed stealth_async function

import asyncio
import logging
import random
import re
from datetime import datetime, timezone
from typing import List, Dict, Any

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from playwright_stealth import Stealth               # ← New import for v2.0+
from fake_useragent import UserAgent
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger("scraper")


@retry(
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1.2, min=4, max=20),
    retry=retry_if_exception_type((PlaywrightTimeoutError, Exception)),
    before_sleep=lambda rs: logger.info(f"Retrying scrape... attempt {rs.attempt_number}")
)
async def fetch_reviews(
    place_url: str,
    limit: int = 100,
    sort_by_newest: bool = True,
    headless: bool = True,
) -> List[Dict[str, Any]]:
    """
    Fetch Google Maps reviews using Playwright + modern stealth (v2.0+)
    """
    all_reviews: List[Dict[str, Any]] = []
    ua = UserAgent()

    async with async_playwright() as p:
        # Apply stealth to the entire playwright instance
        async with Stealth().use_async(p) as stealth_p:
            browser = await stealth_p.chromium.launch(
                headless=headless,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",       # Critical on Railway (limited memory)
                    "--disable-gpu",
                    "--single-process",              # Helps in constrained envs
                    "--disable-background-timer-throttling",
                ],
                timeout=90000,                       # More generous timeout for cold starts
            )

            context = await browser.new_context(
                user_agent=ua.random,
                viewport={"width": 1366, "height": 768},
                locale="en-US",
                timezone_id="Asia/Karachi",
                bypass_csp=True,
                java_script_enabled=True,
            )

            page = await context.new_page()

            try:
                logger.info(f"Navigating → {place_url}")
                await page.goto(place_url, wait_until="domcontentloaded", timeout=60000)

                # Handle cookie/consent banner
                try:
                    await page.get_by_role("button", name=re.compile(r"(Accept|Agree|OK|قبول|同意)", re.I)).click(timeout=10000)
                except:
                    pass

                # Switch to Reviews tab
                try:
                    tab = page.get_by_role("tab", name=re.compile(r"Reviews|مراجعات|評価", re.I))
                    if await tab.is_visible(timeout=12000):
                        await tab.click()
                        await asyncio.sleep(random.uniform(1.8, 3.2))
                except:
                    pass

                # Sort by newest
                if sort_by_newest:
                    try:
                        sort_btn = page.get_by_role("button", name=re.compile(r"Sort|Newest|أحدث", re.I))
                        if await sort_btn.is_visible(timeout=10000):
                            await sort_btn.click()
                            await page.get_by_role("menuitem", name=re.compile(r"Newest|Most recent|أحدث", re.I)).click()
                            await asyncio.sleep(random.uniform(2.0, 4.0))
                    except:
                        pass

                # Scroll to load reviews
                scroll_sel = (
                    "div[role='feed'], div[role='main'] div[aria-label*='reviews'], "
                    "[jsaction*='pane.review'], .m6QErb[aria-label*='Reviews']"
                )
                last_count = 0
                max_attempts = 35

                for _ in range(max_attempts):
                    els = await page.query_selector_all('[data-review-id]')
                    current = len(els)
                    if current >= limit or current <= last_count:
                        break
                    last_count = current

                    await page.evaluate(
                        f"document.querySelector('{scroll_sel}')?.scrollTo(0, document.querySelector('{scroll_sel}')?.scrollHeight || 999999)"
                    )
                    await asyncio.sleep(random.uniform(2.1, 4.9))

                # Parse reviews
                review_els = await page.query_selector_all('[data-review-id]')
                logger.info(f"Parsing {len(review_els)} reviews (limit: {limit})")

                for el in review_els[:limit]:
                    try:
                        review_id = await el.get_attribute("data-review-id") or f"gen_{random.randint(10000,999999)}"

                        # Rating
                        star = await el.query_selector('[aria-label*="star"], [aria-label*="stars"], .lTi8oc span')
                        rating = None
                        if star:
                            aria = await star.get_attribute("aria-label") or ""
                            m = re.search(r"(\d[\d.]*)", aria)
                            rating = int(float(m.group(1))) if m else None

                        # Text
                        text_els = await el.query_selector_all(
                            'span[jsname], div[jsname], .MyEned, .fontBodyMedium, .wiI7pd'
                        )
                        text_parts = []
                        for t in text_els:
                            txt = (await t.inner_text()).strip()
                            if txt and len(txt) > 15 and "translate" not in txt.lower():
                                text_parts.append(txt)

                        clean_text = re.sub(r'\s+', ' ', " ".join(text_parts)).strip()
                        if len(clean_text) < 25:
                            continue

                        # Author
                        author_el = await el.query_selector('.d4r55, .TSUbDb, .fontHeadlineSmall')
                        author = (await author_el.inner_text()).strip() if author_el else "Google User"

                        all_reviews.append({
                            "review_id": review_id,
                            "rating": rating or 0,
                            "text": clean_text,
                            "author": author,
                            "extracted_at": datetime.now(timezone.utc).isoformat(),
                        })

                    except Exception as e:
                        logger.debug(f"Review parse error: {e}")
                        continue

            except Exception as e:
                logger.error(f"Scrape failed for {place_url}: {e}", exc_info=True)
            finally:
                await context.close()
                await browser.close()

    logger.info(f"Extracted {len(all_reviews)} reviews")
    return all_reviews


# For local testing
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_url = "https://www.google.com/maps/place/Lahore+Fort/@31.5882989,74.3104883,17z/..."
    result = asyncio.run(fetch_reviews(test_url, limit=50))
    print(f"Got {len(result)} reviews")
    for r in result[:2]:
        print(r)
