# filename: app/services/scraper.py
import logging
import hashlib
import asyncio
import random
import re
from datetime import datetime, timedelta
from typing import List, Dict, Any
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

logger = logging.getLogger(__name__)


def parse_relative_date(date_text: str) -> datetime:
    now = datetime.utcnow()
    date_text = (date_text or "").lower().strip()
    if not date_text:
        return now

    # Improved parsing for 2026 formats ("2 days ago", "a week ago", "in 3 hours" rare but handled)
    match = re.search(r'(a|an|\d+)\s*(\w+)', date_text)
    if match:
        num_str, unit = match.groups()
        number = 1 if num_str in ('a', 'an') else int(num_str)

        if any(k in unit for k in ['minute', 'min']):
            return now - timedelta(minutes=number)
        if any(k in unit for k in ['hour', 'hr']):
            return now - timedelta(hours=number)
        if 'day' in unit:
            return now - timedelta(days=number)
        if 'week' in unit:
            return now - timedelta(weeks=number)
        if 'month' in unit:
            return now - timedelta(days=number * 30)
        if 'year' in unit:
            return now - timedelta(days=number * 365)

    return now


async def fetch_reviews(
    place_id: str,
    limit: int = 150,
    **kwargs
) -> List[Dict[str, Any]]:
    """
    2026 real-world Playwright Google Reviews scraper.
    Uses selectors & techniques from actively maintained 2026 repos.
    """
    reviews: List[Dict[str, Any]] = []
    seen = set()

    # Direct + reliable URL format
    url = f"https://www.google.com/maps/place/?q=place_id:{place_id}"

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-gpu",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled",
                ]
            )

            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                viewport={"width": 1366, "height": 768},
                locale="en-US",
                timezone_id="Asia/Karachi",
                bypass_csp=True,
            )

            # Minimal but effective stealth (what most 2026 coders add)
            await context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
                window.chrome = { runtime: {} };
            """)

            page = await context.new_page()
            logger.info(f"Starting reviews scrape for place_id: {place_id}")

            await page.goto(url, wait_until="domcontentloaded", timeout=60000)

            # Accept cookies / consent
            try:
                await page.get_by_role("button", name=re.compile(r"(accept|agree|ok|continue)", re.I)).click(timeout=10000)
                await asyncio.sleep(random.uniform(1.0, 2.5))
            except:
                pass

            # Open Reviews tab – chain of most reliable locators in 2026
            tab_found = False
            for loc in [
                page.get_by_role("tab", name=re.compile(r"reviews?", re.I)),
                page.get_by_role("tab", name=re.compile(r"\d.*reviews?", re.I)),
                page.locator('[aria-label*="review" i]'),
                page.get_by_text("Reviews").first,
            ]:
                try:
                    if await loc.is_visible(timeout=6000):
                        await loc.click(timeout=10000)
                        await asyncio.sleep(random.uniform(2.0, 3.8))
                        await page.wait_for_selector("div.jftiEf, [data-review-id]", timeout=15000)
                        tab_found = True
                        break
                except:
                    continue

            if not tab_found:
                logger.warning("Reviews tab could not be opened")
                await browser.close()
                return []

            # Scroll + collect loop (human-like)
            attempts_no_new = 0
            prev_len = 0

            while len(reviews) < limit and attempts_no_new < 15:
                # Click "More" buttons
                more = page.get_by_role("button", name=re.compile(r"more", re.I))
                for i in range(min(await more.count(), 10)):
                    try:
                        await more.nth(i).click(timeout=4000)
                        await asyncio.sleep(0.5)
                    except:
                        pass

                # Extract using current stable selectors
                cards = await page.query_selector_all("div.jftiEf, [data-review-id]")

                for card in cards:
                    try:
                        author_el = await card.query_selector(".d4r55")
                        author = (await author_el.inner_text() if author_el else "Anonymous").strip()

                        text_el = await card.query_selector(".wiI7pd")
                        text = (await text_el.inner_text() if text_el else "").strip()

                        rating_el = await card.query_selector('[aria-label*="star"]')
                        rating_text = await rating_el.get_attribute("aria-label") if rating_el else ""
                        rating = int(re.search(r"\d+", rating_text).group()) if re.search(r"\d+", rating_text) else 0

                        date_el = await card.query_selector(".rsqaWe")
                        date_str = (await date_el.inner_text() if date_el else "").strip()
                        time_iso = parse_relative_date(date_str).isoformat()

                        unique_key = hashlib.sha256(f"{author}|{text[:120]}|{rating}".encode()).hexdigest()
                        if unique_key in seen:
                            continue

                        reviews.append({
                            "review_id": unique_key,
                            "rating": rating,
                            "text": text,
                            "author_name": author,
                            "google_review_time": time_iso,
                        })
                        seen.add(unique_key)

                    except:
                        continue

                current_len = len(reviews)
                if current_len == prev_len:
                    attempts_no_new += 1
                else:
                    attempts_no_new = 0
                prev_len = current_len

                # Scroll
                delta = random.randint(1800, 3200)
                await page.mouse.wheel(0, delta)
                await asyncio.sleep(random.uniform(2.2, 4.5))

            logger.info(f"Collected {len(reviews)} reviews")
            await browser.close()
            return reviews[:limit]

    except Exception as e:
        logger.error(f"Scraper error: {e}", exc_info=True)
        return []
