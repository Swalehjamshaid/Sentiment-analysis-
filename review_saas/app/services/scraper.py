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

    # Handle "a minute ago", "2 hours ago", etc.
    match = re.search(r'(\d+|a|an)\s*(\w+)', date_text)
    if match:
        num_str, unit = match.groups()
        number = 1 if num_str in ('a', 'an') else int(num_str)
        
        if 'minute' in unit or 'min' in unit:
            return now - timedelta(minutes=number)
        if 'hour' in unit or 'hr' in unit:
            return now - timedelta(hours=number)
        if 'day' in unit:
            return now - timedelta(days=number)
        if 'week' in unit:
            return now - timedelta(weeks=number)
        if 'month' in unit:
            return now - timedelta(days=number * 30)
        if 'year' in unit:
            return now - timedelta(days=number * 365)

    return now  # fallback


async def fetch_reviews(
    place_id: str,
    limit: int = 150,
    **kwargs
) -> List[Dict[str, Any]]:
    """
    Playwright-based Google Maps reviews scraper – 2026 hardened version.
    Uses multiple locator strategies and basic stealth.
    """
    reviews: List[Dict[str, Any]] = []
    collected_hashes = set()

    # Modern direct place URL format (works better in 2026)
    place_url = f"https://www.google.com/maps/place/?q=place_id:{place_id}"

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
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                ),
                viewport={'width': 1366, 'height': 768},
                locale="en-US",
                timezone_id="Asia/Karachi",
                bypass_csp=True,
                java_script_enabled=True,
            )

            # Basic stealth init script
            await context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
                Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3] });
                window.chrome = { runtime: {} };
            """)

            page = await context.new_page()
            logger.info(f"Starting scrape → Place ID: {place_id}")

            await page.goto(place_url, wait_until="domcontentloaded", timeout=60000)

            # Consent / "Accept all"
            try:
                await page.get_by_role("button", name=re.compile(r"accept|agree|ok|continue|got it", re.I)).click(timeout=10000)
                await asyncio.sleep(random.uniform(1.2, 2.5))
            except:
                pass

            # ── Robust Reviews tab opening (2026 strategies) ──
            opened = False
            tab_strategies = [
                page.get_by_role("tab", name=re.compile(r"reviews?|bewertungen|avis|recensioni|reseñas|تقييمات|مراجعات", re.I)),
                page.get_by_role("tab", name=re.compile(r"\d+[,\.]?\d*\s*(reviews?|bewertungen|avis)", re.I)),
                page.locator('[aria-label*="review" i], [aria-label*="bewertung" i]'),
                page.get_by_text(re.compile(r"reviews?|bewertungen|avis", re.I), exact=False).first,
            ]

            for locator_fn in tab_strategies:
                try:
                    locator = locator_fn
                    if await locator.is_visible(timeout=8000):
                        await locator.click(delay=random.randint(100, 400), timeout=12000)
                        await asyncio.sleep(random.uniform(2.0, 4.0))
                        # Wait for review container
                        await page.wait_for_selector(
                            'div.jftiEf, [data-review-id], div[role="listitem"], div[jscontroller*="review"]',
                            state="visible", timeout=20000
                        )
                        opened = True
                        logger.info("Reviews tab opened")
                        break
                except Exception as exc:
                    logger.debug(f"Tab strategy failed: {exc}")
                    continue

            if not opened:
                logger.warning("Failed to open reviews panel after all attempts")
                await browser.close()
                return []

            # ── Collection loop ──
            scroll_attempts = 0
            prev_review_count = 0
            max_no_progress = 12  # stop if no new reviews for ~12 scrolls

            while len(reviews) < limit and scroll_attempts < 80:
                # Expand "More" buttons (limit to ~10 to avoid over-click)
                more_btns = page.get_by_role("button", name=re.compile(r"more|mehr|plus|ver más", re.I))
                for i in range(min(await more_btns.count(), 10)):
                    try:
                        await more_btns.nth(i).click(timeout=5000, force=True)
                        await asyncio.sleep(0.5 + random.random() * 0.8)
                    except:
                        pass

                # Review card selectors (most stable in late 2025 / 2026)
                cards = await page.query_selector_all(
                    'div.jftiEf, [data-review-id], div[role="listitem"], div[jsaction*="review"]'
                )

                added_this_round = 0

                for card in cards:
                    try:
                        # Author – very stable via role or common classes
                        author_loc = await card.query_selector(
                            '[role="heading"], .d4r55, .TSUbDb, strong, span[class*="font-bold"]'
                        )
                        author = (await author_loc.inner_text() if author_loc else "Anonymous").strip()

                        # Review text
                        text_loc = await card.query_selector(
                            '.wiI7pd, [jsname*="reviewText"], div[class*="text"], span:not([aria-hidden])'
                        )
                        text = (await text_loc.inner_text() if text_loc else "").strip()

                        # Rating – aria-label is extremely reliable
                        stars = await card.query_selector('[role="img"][aria-label*="star"]')
                        rating_str = await stars.get_attribute("aria-label") if stars else ""
                        rating_match = re.search(r'(\d+(\.\d+)?)', rating_str)
                        rating = int(float(rating_match.group(1))) if rating_match else 0

                        # Date
                        date_loc = await card.query_selector(
                            '.rsqaWe, [class*="r0j7D"], span[aria-label*="ago"], .DU9Pgb span'
                        )
                        date_text = (await date_loc.inner_text() if date_loc else "").strip()
                        review_time_iso = parse_relative_date(date_text).isoformat()

                        # Unique hash (author + first 120 chars text + rating)
                        rev_hash = hashlib.sha256(
                            f"{author}|{text[:120]}|{rating}".encode()
                        ).hexdigest()

                        if rev_hash in collected_hashes:
                            continue

                        reviews.append({
                            "review_id": rev_hash,
                            "rating": rating,
                            "text": text,
                            "author_name": author,
                            "google_review_time": review_time_iso,
                        })
                        collected_hashes.add(rev_hash)
                        added_this_round += 1

                    except Exception:
                        continue

                current_total = len(reviews)

                if added_this_round == 0:
                    scroll_attempts += 1
                else:
                    scroll_attempts = max(0, scroll_attempts - 2)  # reward progress

                if current_total == prev_review_count:
                    if scroll_attempts >= max_no_progress:
                        logger.info("No new reviews for several scrolls → stopping")
                        break
                else:
                    prev_review_count = current_total

                # Human-like scroll
                scroll_delta = random.randint(1600, 3400)
                await page.mouse.wheel(0, scroll_delta)
                await asyncio.sleep(random.uniform(2.1, 4.8))

            logger.info(f"Finished – collected {len(reviews)} reviews")
            await browser.close()
            return reviews[:limit]

    except Exception as e:
        logger.error(f"Scraper crashed: {str(e)}", exc_info=True)
        return []
