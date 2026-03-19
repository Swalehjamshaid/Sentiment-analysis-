# filename: app/services/scraper.py  (or wherever this lives)
import logging
import hashlib
import asyncio
import random
import re
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

logger = logging.getLogger(__name__)


def parse_relative_date(date_text: str) -> datetime:
    now = datetime.utcnow()
    date_text = (date_text or "").lower().strip()
    if not date_text:
        return now

    number = 1
    for part in date_text.split():
        if part.isdigit():
            number = int(part)
            break
        if part.startswith("a") or part.startswith("an"):  # "a week ago"
            number = 1

    if any(x in date_text for x in ["hour", "hr"]):
        return now - timedelta(hours=number)
    if any(x in date_text for x in ["day", "d"]):
        return now - timedelta(days=number)
    if "week" in date_text:
        return now - timedelta(weeks=number)
    if "month" in date_text:
        return now - timedelta(days=number * 30)
    if "year" in date_text:
        return now - timedelta(days=number * 365)
    if "ago" in date_text and number == 1:  # fallback for "ago"
        return now - timedelta(days=1)
    return now


async def fetch_reviews(
    place_id: str,
    limit: int = 150,
    **kwargs
) -> List[Dict[str, Any]]:
    reviews: List[Dict[str, Any]] = []
    collected_ids = set()

    # Direct place URL (works well in most regions)
    place_url = f"https://www.google.com/maps/place/?q=place_id:{place_id}"

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"]
            )
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/128.0.0.0 Safari/537.36"
                ),
                viewport={'width': 1280, 'height': 900},
                locale="en-US",
                timezone_id="Asia/Karachi",  # PKT friendly
            )

            page = await context.new_page()
            logger.info(f"🚀 Starting Playwright → Place ID: {place_id}")

            await page.goto(place_url, wait_until="domcontentloaded", timeout=45000)

            # Handle consent / cookies banner
            try:
                await page.get_by_role("button", name=re.compile("accept|agree|ok", re.I)).click(timeout=8000)
                await asyncio.sleep(1.5)
            except:
                pass

            # ────────────────────────────────────────
            # Open Reviews tab – robust multi-strategy
            # ────────────────────────────────────────
            review_panel_visible = False

            strategies = [
                lambda: page.get_by_role("tab", name=re.compile(r"reviews?|bewertungen|avis|reseñas", re.I)),
                lambda: page.get_by_role("tab", name=re.compile(r"\d+[,\s]*\d*\s*reviews?", re.I)),
                lambda: page.locator('button[aria-label*="reviews" i]'),
                lambda: page.get_by_text("Reviews", exact=False),
            ]

            for strat in strategies:
                try:
                    tab = strat()
                    if await tab.is_visible(timeout=5000):
                        await tab.click(timeout=10000)
                        await asyncio.sleep(2.5 + random.uniform(0, 1))
                        # Wait for review cards to appear
                        await page.wait_for_selector(
                            'div.jftiEf, [data-review-id], div[role="listitem"]',
                            timeout=15000
                        )
                        review_panel_visible = True
                        logger.info("→ Reviews panel opened successfully")
                        break
                except Exception as e:
                    logger.debug(f"Strategy failed: {e}")
                    continue

            if not review_panel_visible:
                logger.warning("⚠️ Could not open reviews tab after all attempts")
                await browser.close()
                return []

            # ────────────────────────────────────────
            # Scroll + expand + collect loop
            # ────────────────────────────────────────
            scroll_attempts = 0
            last_count = 0

            while len(reviews) < limit and scroll_attempts < 60:
                # Click all "More" buttons
                more_buttons = page.get_by_role("button", name=re.compile("more", re.I))
                count_more = await more_buttons.count()
                for i in range(min(count_more, 8)):  # don't over-click
                    try:
                        await more_buttons.nth(i).click(timeout=4000)
                        await asyncio.sleep(0.4)
                    except:
                        pass

                # Collect review cards
                review_elements = await page.query_selector_all(
                    'div.jftiEf, [data-review-id], div[role="listitem"]'
                )

                for el in review_elements:
                    try:
                        # Author (most stable: first big text in card)
                        author_el = await el.query_selector(
                            '[class*="d4r55"], .TSUbDb, [role="heading"], strong'
                        )
                        author = (await author_el.inner_text() if author_el else "Anonymous").strip()

                        # Text
                        text_el = await el.query_selector(
                            '.wiI7pd, [jscontroller*="reviewText"], span:not([aria-hidden])'
                        )
                        text = (await text_el.inner_text() if text_el else "").strip()

                        # Rating via aria-label (very stable)
                        rating_el = await el.query_selector('[aria-label*="star"]')
                        rating_raw = await rating_el.get_attribute("aria-label") if rating_el else ""
                        rating_match = re.search(r"(\d+(\.\d+)?)", rating_raw)
                        rating = int(float(rating_match.group(1))) if rating_match else 0

                        # Date
                        date_el = await el.query_selector(
                            '.rsqaWe, [class*="r0j7D"], span[aria-label*="ago"]'
                        )
                        date_text = (await date_el.inner_text() if date_el else "").strip()
                        review_time = parse_relative_date(date_text).isoformat()

                        # Deduplicate
                        review_hash = hashlib.md5(
                            f"{author}|{text[:100]}|{rating}".encode()
                        ).hexdigest()

                        if review_hash in collected_ids:
                            continue

                        reviews.append({
                            "review_id": review_hash,
                            "rating": rating,
                            "text": text,
                            "author_name": author,
                            "google_review_time": review_time,
                        })
                        collected_ids.add(review_hash)

                    except Exception:
                        continue

                current_count = len(reviews)
                if current_count == last_count:
                    scroll_attempts += 1
                else:
                    scroll_attempts = 0  # reset if we got new ones
                last_count = current_count

                if current_count >= limit:
                    break

                # Smart scroll inside review pane
                try:
                    await page.mouse.wheel(0, random.randint(1800, 3200))
                    await asyncio.sleep(random.uniform(1.8, 3.4))
                except:
                    await page.evaluate("window.scrollBy(0, 2800)")
                    await asyncio.sleep(2.2)

            logger.info(f"✅ Fetched {len(reviews)} reviews for {place_id}")
            await browser.close()
            return reviews[:limit]

    except Exception as e:
        logger.error(f"❌ Playwright scraper failed: {str(e)}", exc_info=True)
        return []
