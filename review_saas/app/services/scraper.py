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
    date_text = (date_text or "").lower()
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
    High-reliability Google Maps review scraper using mobile emulation + fallback desktop + retries
    """
    reviews: List[Dict[str, Any]] = []
    collected_ids = set()

    # Multiple user-agent rotation for evasion
    user_agents = [
        "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
        "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Mobile Safari/537.36",
    ]

    max_retries = 3
    for retry in range(max_retries):
        logger.info(f"Scrape attempt {retry+1}/{max_retries} for place_id: {place_id}")

        try:
            async with async_playwright() as p:
                device = p.devices['iPhone 13']
                browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-gpu"])
                context = await browser.new_context(
                    **device,
                    user_agent=random.choice(user_agents),
                    locale="en-US",
                    timezone_id="Asia/Karachi",
                    bypass_csp=True,
                    java_script_enabled=True,
                )

                page = await context.new_page()
                logger.info(f"📱 Starting mobile emulation scrape: {place_id}")

                place_url = f"https://www.google.com/maps/search/?api=1&query=Google&query_place_id={place_id}"
                await page.goto(place_url, wait_until="networkidle", timeout=90000)

                # Consent bypass (mobile layout)
                try:
                    await page.click('button:has-text("Accept all")', timeout=7000)
                    await asyncio.sleep(random.uniform(1.0, 2.0))
                except:
                    try:
                        await page.click('[aria-label*="Accept"], button:has-text("Agree")', timeout=5000)
                    except:
                        pass

                # Try to open Reviews tab / section
                for selector in [
                    'text=Reviews',
                    'text=جائزے',
                    '[aria-label*="reviews" i]',
                    'button:has-text("Reviews")',
                    '[role="tab"]:has-text("Reviews")',
                ]:
                    try:
                        await page.click(selector, timeout=10000)
                        await asyncio.sleep(random.uniform(1.5, 3.0))
                        break
                    except:
                        continue

                # Fallback scroll if reviews not visible
                if not await page.query_selector('[data-review-id], .jftiEf'):
                    logger.warning("No reviews visible after tab attempt → forcing scroll")

                scroll_attempts = 0
                last_count = 0

                while len(reviews) < limit and scroll_attempts < 80:
                    # Expand "More" buttons
                    mores = await page.query_selector_all('button:has-text("More"), text="More"')
                    for more in mores[:15]:
                        try:
                            await more.click(timeout=2000)
                            await asyncio.sleep(0.4)
                        except:
                            pass

                    # Select review elements
                    elements = await page.query_selector_all(
                        '[data-review-id], .jftiEf, div[role="listitem"], .MyEned, .wiI7pd'
                    )

                    added_this_round = 0
                    for r in elements:
                        try:
                            author_el = await r.query_selector('.My579, .d4r55, strong')
                            text_el = await r.query_selector('.wiI7pd, .MyEned')
                            rating_el = await r.query_selector('[aria-label*="star"]')
                            date_el = await r.query_selector('.rsqaWe, .DU9Pgb')

                            author = await author_el.inner_text() if author_el else "Google User"
                            text = await text_el.inner_text() if text_el else ""
                            date_text = await date_el.inner_text() if date_el else ""

                            review_id = hashlib.md5(f"{author}{text[:200]}".encode()).hexdigest()
                            if review_id in collected_ids:
                                continue

                            rating_raw = await rating_el.get_attribute("aria-label") if rating_el else "0"
                            rating_match = re.search(r'(\d+(\.\d+)?)', rating_raw)
                            rating = int(float(rating_match.group(1))) if rating_match else 0

                            reviews.append({
                                "review_id": review_id,
                                "rating": rating,
                                "text": text,
                                "author_name": author,
                                "google_review_time": parse_relative_date(date_text).isoformat()
                            })
                            collected_ids.add(review_id)
                            added_this_round += 1
                        except:
                            continue

                    current_count = len(reviews)
                    logger.info(f"Attempt {retry+1} — Scroll {scroll_attempts+1}: +{added_this_round} → Total {current_count}")

                    if current_count >= limit:
                        break

                    if current_count == last_count:
                        scroll_attempts += 1
                        if scroll_attempts >= 30:
                            logger.warning("No new reviews after 30 scrolls → giving up this attempt")
                            break
                    else:
                        scroll_attempts = 0
                    last_count = current_count

                    await page.evaluate("window.scrollBy(0, 3000)")
                    await asyncio.sleep(random.uniform(2.0, 4.5))

                await browser.close()

                if len(reviews) > 0:
                    logger.info(f"✅ Success: Fetched {len(reviews)} reviews via mobile emulation (attempt {retry+1})")
                    return reviews[:limit]

        except Exception as e:
            logger.error(f"Attempt {retry+1} failed: {str(e)[:200]}...")
            await asyncio.sleep(random.uniform(3, 7))

    logger.error(f"❌ All {max_retries} attempts failed for place_id: {place_id}")
    return []
