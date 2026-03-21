# filename: app/services/scraper.py
import logging
import hashlib
import asyncio
import random
import re
from datetime import datetime, timedelta
from typing import List, Dict, Any

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from playwright_stealth import stealth_async
from undetected_playwright import async_playwright as undetected_async_playwright
from fake_useragent import UserAgent
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger(__name__)


def parse_relative_date(date_text: str) -> datetime:
    now = datetime.utcnow()
    date_text = (date_text or "").lower().strip()
    number = 1
    for part in date_text.split():
        if part.isdigit():
            number = int(part)
            break
    if "hour" in date_text:
        return now - timedelta(hours=number)
    if "day" in date_text:
        return now - timedelta(days=number)
    if "week" in date_text:
        return now - timedelta(weeks=number)
    if "month" in date_text:
        return now - timedelta(days=number * 30)
    if "year" in date_text:
        return now - timedelta(days=number * 365)
    return now


@retry(
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=3, max=15),
    retry=retry_if_exception_type(Exception),
    reraise=True,
)
async def fetch_reviews(place_id: str, limit: int = 200, **kwargs) -> List[Dict[str, Any]]:
    """
    Powerful Google Maps Reviews Scraper - 2026 edition
    """
    reviews: List[Dict[str, Any]] = []
    collected_ids = set()

    ua = UserAgent()
    user_agents = [ua.random for _ in range(5)]

    async with undetected_async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"]
        )
        context = await browser.new_context(
            user_agent=random.choice(user_agents),
            viewport={"width": 390, "height": 844},
            locale="en-US",
            timezone_id="Asia/Karachi",
            bypass_csp=True,
            java_script_enabled=True,
        )

        page = await context.new_page()
        await stealth_async(page)

        logger.info(f"Stealth scrape for {place_id} (UA: {context._options.get('userAgent')[:50]}...)")

        url = f"https://www.google.com/maps/place/?q=place_id:{place_id}"
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)

        # Consent
        consent_selectors = [
            'button:has-text("Accept all")',
            'button:has-text("Agree")',
            '[aria-label*="Accept"], [aria-label*="Continue"]',
        ]
        for sel in consent_selectors:
            try:
                await page.click(sel, timeout=7000)
                await asyncio.sleep(random.uniform(0.8, 1.8))
                break
            except:
                pass

        # Open reviews
        review_selectors = [
            'text=Reviews',
            'text=جائزے',
            'text=تقييمات',
            '[aria-label*="reviews" i]',
            'button:has-text("Reviews")',
            '[role="tab"]:has-text("Reviews")',
        ]

        opened = False
        for sel in review_selectors:
            try:
                elem = page.locator(sel).first
                if await elem.is_visible(timeout=8000):
                    await elem.click(timeout=12000)
                    await asyncio.sleep(random.uniform(1.5, 3.5))
                    opened = True
                    logger.info("Reviews panel opened")
                    break
            except:
                continue

        if not opened:
            logger.warning("No tab found - forcing scroll")

        # Scroll & collect
        scroll_attempts = 0
        last_count = 0

        while len(reviews) < limit and scroll_attempts < 100:
            # Expand More
            mores = page.get_by_role("button", name=re.compile(r"more|مزید|See more", re.I))
            for i in range(min(await mores.count(), 25)):
                try:
                    await mores.nth(i).click(timeout=2500)
                    await asyncio.sleep(0.35)
                except:
                    pass

            cards = await page.query_selector_all(
                '[data-review-id], .jftiEf, [role="listitem"], .review-card, .MyEned'
            )

            added = 0
            for card in cards:
                try:
                    author_el = await card.query_selector('.d4r55, .My579, strong, .TSUbDb')
                    text_el = await card.query_selector('.wiI7pd, .MyEned')
                    rating_el = await card.query_selector('[aria-label*="star"]')
                    date_el = await card.query_selector('.rsqaWe, .DU9Pgb')

                    author = (await author_el.inner_text() if author_el else "Anonymous").strip()
                    text = (await text_el.inner_text() if text_el else "").strip()
                    rating_raw = await rating_el.get_attribute("aria-label") if rating_el else ""
                    rating = int(re.search(r'\d+', rating_raw).group()) if re.search(r'\d+', rating_raw) else 0
                    date_text = (await date_el.inner_text() if date_el else "").strip()

                    rid = hashlib.md5(f"{author}{text[:200]}".encode()).hexdigest()
                    if rid in collected_ids:
                        continue

                    reviews.append({
                        "review_id": rid,
                        "rating": rating,
                        "text": text,
                        "author_name": author,
                        "google_review_time": parse_relative_date(date_text).isoformat()
                    })
                    collected_ids.add(rid)
                    added += 1

                except Exception:
                    continue

            current = len(reviews)
            logger.info(f"Scroll {scroll_attempts+1}: +{added} → Total {current}")

            if current >= limit:
                break

            if current == last_count:
                scroll_attempts += 1
                if scroll_attempts >= 40:
                    logger.warning("No new reviews after 40 scrolls → stopping")
                    break
            else:
                scroll_attempts = 0
            last_count = current

            await page.evaluate("window.scrollBy(0, 4000)")
            await asyncio.sleep(random.uniform(2.5, 5.0))

        await browser.close()

        logger.info(f"Finished: {len(reviews)} reviews collected")
        return reviews[:limit]
