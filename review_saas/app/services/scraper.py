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


async def fetch_reviews(place_id: str, limit: int = 150, **kwargs) -> List[Dict[str, Any]]:
    """
    Powerful Google Maps Reviews Scraper using playwright + playwright-stealth
    Maximizes success rate in 2026 environment
    """
    reviews: List[Dict[str, Any]] = []
    collected_ids = set()

    # Rotate user agents to look more natural
    user_agents = [
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
        "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Mobile Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    ]

    max_retries = 3
    for attempt in range(max_retries):
        logger.info(f"Scrape attempt {attempt + 1}/{max_retries} for place_id: {place_id}")

        try:
            async with async_playwright() as p:
                # Use mobile emulation – Google is less aggressive on mobile
                device = p.devices["iPhone 13"]
                browser = await p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"]
                )
                context = await browser.new_context(
                    **device,
                    user_agent=random.choice(user_agents),
                    locale="en-US",
                    timezone_id="Asia/Karachi",
                    bypass_csp=True,
                    java_script_enabled=True,
                )

                page = await context.new_page()

                # Apply stealth – this is the most important part
                await stealth_async(page)

                logger.info(f"Using UA: {context._options.get('userAgent')}")

                url = f"https://www.google.com/maps/place/?q=place_id:{place_id}"
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)

                # Consent handling – multiple selectors
                consent_selectors = [
                    'button:has-text("Accept all")',
                    'button:has-text("Agree")',
                    'button[aria-label*="Accept"]',
                    '[role="button"]:has-text("Accept")',
                ]
                for sel in consent_selectors:
                    try:
                        await page.click(sel, timeout=6000)
                        await asyncio.sleep(random.uniform(0.8, 1.8))
                        break
                    except:
                        pass

                # Open reviews tab – very resilient selection
                review_selectors = [
                    'text=Reviews',
                    'text=جائزے',
                    'text=تقييمات',
                    '[aria-label*="reviews" i]',
                    'button:has-text("Reviews")',
                    '[role="tab"]:has-text("Reviews")',
                    '[role="button"]:has-text("Reviews")',
                ]

                tab_opened = False
                for selector in review_selectors:
                    try:
                        elem = page.locator(selector).first
                        if await elem.is_visible(timeout=8000):
                            await elem.click(timeout=12000)
                            await asyncio.sleep(random.uniform(1.5, 3.5))
                            tab_opened = True
                            logger.info("Reviews section opened")
                            break
                    except:
                        continue

                if not tab_opened:
                    logger.warning("No reviews tab found – attempting direct scroll")

                # Scroll & collect loop
                scroll_attempts = 0
                last_count = 0

                while len(reviews) < limit and scroll_attempts < 90:
                    # Expand all "More" buttons
                    mores = await page.query_selector_all('button:has-text("More"), text="More", text="مزید"')
                    for more in mores[:20]:
                        try:
                            await more.click(timeout=2500)
                            await asyncio.sleep(0.35)
                        except:
                            pass

                    # Collect review cards (multiple selectors for resilience)
                    cards = await page.query_selector_all(
                        '[data-review-id], .jftiEf, div[role="listitem"], .review-card, .MyEned'
                    )

                    added_this_round = 0
                    for card in cards:
                        try:
                            # Author
                            author_el = await card.query_selector('.d4r55, .My579, strong, .TSUbDb')
                            author = (await author_el.inner_text() if author_el else "Anonymous").strip()

                            # Text
                            text_el = await card.query_selector('.wiI7pd, .MyEned')
                            text = (await text_el.inner_text() if text_el else "").strip()

                            # Rating
                            rating_el = await card.query_selector('[aria-label*="star rating"], [aria-label*="star"]')
                            rating_raw = await rating_el.get_attribute("aria-label") if rating_el else ""
                            rating_match = re.search(r"(\d+(\.\d+)?)", rating_raw)
                            rating = int(float(rating_match.group(1))) if rating_match else 0

                            # Date
                            date_el = await card.query_selector('.rsqaWe, .DU9Pgb, [aria-label*="ago"]')
                            date_text = (await date_el.inner_text() if date_el else "").strip()

                            review_id = hashlib.md5(f"{author}{text[:200]}".encode()).hexdigest()
                            if review_id in collected_ids:
                                continue

                            reviews.append({
                                "review_id": review_id,
                                "rating": rating,
                                "text": text,
                                "author_name": author,
                                "google_review_time": parse_relative_date(date_text).isoformat()
                            })
                            collected_ids.add(review_id)
                            added_this_round += 1

                        except Exception:
                            continue

                    current_count = len(reviews)
                    logger.info(f"Attempt {attempt+1} — Scroll {scroll_attempts+1}: +{added_this_round} → Total {current_count}")

                    if current_count >= limit:
                        break

                    if current_count == last_count:
                        scroll_attempts += 1
                        if scroll_attempts >= 35:
                            logger.warning("No new reviews for 35 scrolls – stopping this attempt")
                            break
                    else:
                        scroll_attempts = 0
                    last_count = current_count

                    # Scroll aggressively but naturally
                    await page.evaluate("window.scrollBy(0, 3500)")
                    await asyncio.sleep(random.uniform(2.2, 4.8))

                await browser.close()

                if len(reviews) > 0:
                    logger.info(f"Success on attempt {attempt+1}: {len(reviews)} reviews collected")
                    return reviews[:limit]

        except Exception as e:
            logger.error(f"Attempt {attempt+1} failed: {str(e)[:200]}...")
            await asyncio.sleep(random.uniform(4, 9))

    logger.error(f"All {max_retries} attempts failed for {place_id}")
    return []
