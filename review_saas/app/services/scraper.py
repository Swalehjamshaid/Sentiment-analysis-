import logging
import hashlib
import re
from datetime import datetime, timedelta
from typing import List, Dict, Any
from playwright.async_api import async_playwright

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


async def fetch_reviews(
    place_id: str,
    limit: int = 100,
    **kwargs
) -> List[Dict[str, Any]]:

    reviews: List[Dict[str, Any]] = []
    place_url = f"https://www.google.com/maps/place/?q=place_id:{place_id}"

    try:
        async with async_playwright() as p:

            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"]
            )

            context = await browser.new_context(
                locale="en-US",
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
            )

            # 🚀 Block heavy resources
            await context.route(
                "**/*",
                lambda route: route.abort()
                if route.request.resource_type in ["image", "stylesheet", "font"]
                else route.continue_()
            )

            page = await context.new_page()

            logger.info(f"🚀 Fetching reviews for Place ID: {place_id}")

            await page.goto(place_url, wait_until="domcontentloaded", timeout=60000)

            # Accept cookies
            try:
                await page.click('button:has-text("Accept")', timeout=3000)
            except:
                pass

            # ✅ CLICK REVIEWS TAB (UPDATED LOGIC)
            try:
                await page.click('button[aria-label*="reviews"]', timeout=10000)
                await page.wait_for_timeout(2000)
            except:
                logger.warning("⚠️ Reviews tab not clickable, trying fallback...")
                try:
                    await page.click('a[href*="reviews"]', timeout=5000)
                except:
                    logger.error("❌ Cannot open reviews section")
                    await browser.close()
                    return []

            collected_ids = set()
            scroll_attempts = 0
            max_scroll = 20

            # ✅ TARGET SCROLLABLE REVIEWS PANEL
            review_container_selector = 'div[role="feed"]'

            while len(reviews) < limit and scroll_attempts < max_scroll:

                try:
                    container = await page.query_selector(review_container_selector)

                    if container:
                        await container.evaluate(
                            "(el) => el.scrollBy(0, 1500)"
                        )
                    else:
                        await page.mouse.wheel(0, 1500)

                except:
                    pass

                await page.wait_for_timeout(1500)

                # Expand "More"
                mores = await page.query_selector_all('button:has-text("More")')
                for m in mores:
                    try:
                        await m.click(timeout=300)
                    except:
                        pass

                # ✅ UPDATED REVIEW SELECTOR
                elements = await page.query_selector_all('div.jftiEf')

                for r in elements:
                    try:
                        author_el = await r.query_selector('.d4r55')
                        text_el = await r.query_selector('.wiI7pd')
                        date_el = await r.query_selector('.rsqaWe')
                        rating_el = await r.query_selector('[aria-label*="star"]')

                        author = await author_el.inner_text() if author_el else "Google User"
                        text = await text_el.inner_text() if text_el else ""
                        date_text = await date_el.inner_text() if date_el else ""

                        review_id = hashlib.md5(f"{author}{text}".encode()).hexdigest()
                        if review_id in collected_ids:
                            continue

                        rating_raw = ""
                        if rating_el:
                            rating_raw = await rating_el.get_attribute("aria-label") or ""

                        match = re.search(r"\d", rating_raw)
                        rating = int(match.group()) if match else 0

                        reviews.append({
                            "review_id": review_id,
                            "rating": rating,
                            "text": text,
                            "author_name": author,
                            "google_review_time": parse_relative_date(date_text).isoformat()
                        })

                        collected_ids.add(review_id)

                        if len(reviews) >= limit:
                            break

                    except:
                        continue

                scroll_attempts += 1

            await browser.close()

            logger.info(f"✅ Fetched {len(reviews)} reviews successfully")
            return reviews

    except Exception as e:
        logger.error(f"❌ Scraper Failure: {str(e)}")
        return []
