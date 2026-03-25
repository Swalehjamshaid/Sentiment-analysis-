import asyncio
import re
import random
import logging
import csv
from datetime import datetime

# =================================================================
# GLOBAL CONFIGURATION & LOGGING
# =================================================================
logger = logging.getLogger("ReviewSaaS.Scraper")

# =================================================================
# RESIDENTIAL PROXY POOL
# =================================================================
PROXIES = [
    "http://dkgjitgr:uzeqkqwjwmqe@31.59.20.176:6754",
    "http://dkgjitgr:uzeqkqwjwmqe@23.95.150.145:6114",
    "http://dkgjitgr:uzeqkqwjwmqe@198.23.239.134:6540",
    "http://dkgjitgr:uzeqkqwjwmqe@45.38.107.97:6014",
    "http://dkgjitgr:uzeqkqwjwmqe@107.172.163.27:6543"
]

# =================================================================
# PLAYWRIGHT
# =================================================================
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async


async def fetch_reviews(place_id: str, limit: int = 50):
    logger.info(f"🚀 Starting scraper for Place ID: {place_id} | Target: {limit}")

    reviews_data = []
    visited_ids = set()
    selected_proxy = random.choice(PROXIES)

    async with async_playwright() as p:

        # ✅ FIX: fallback if proxy fails
        try:
            browser = await p.firefox.launch(
                headless=True,
                proxy={"server": selected_proxy}
            )
        except Exception:
            logger.warning("⚠️ Proxy failed, launching without proxy...")
            browser = await p.firefox.launch(headless=True)

        context = await browser.new_context(
            viewport={"width": 1280, "height": 1280},
            locale="en-US",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:135.0) Gecko/20100101 Firefox/135.0",
            extra_http_headers={"Accept-Language": "en-US,en;q=0.9"}
        )

        page = await context.new_page()
        await stealth_async(page)

        try:
            url = f"https://www.google.com/maps/place/?q=place_id:{place_id}&hl=en"
            await page.goto(url, wait_until="networkidle", timeout=90000)

            await page.locator('button[aria-label*="Reviews for"]').click(timeout=15000)
            await asyncio.sleep(random.uniform(3, 5))

            scroll_attempts = 0
            max_attempts = (limit // 10) + 15

            while len(reviews_data) < limit and scroll_attempts < max_attempts:

                # Expand "More"
                more_buttons = page.locator("button.w8nwRe.kyuRq, button[data-review-id] button")
                for btn in await more_buttons.all():
                    try:
                        await btn.click(timeout=2000)
                    except:
                        pass

                review_cards = page.locator("div.jJc9Ad, div.jftiEf, div[data-review-id]")
                cards = await review_cards.all()

                new_found = False

                for card in cards:
                    try:
                        review_id = await card.get_attribute("data-review-id") or f"rev_{len(reviews_data)}"

                        if review_id in visited_ids:
                            continue

                        author = "N/A"
                        author_el = card.locator("div.d4r55, span.X43Kjb, div.fontBodyMedium")
                        if await author_el.count() > 0:
                            author = (await author_el.first.inner_text()).strip()

                        rating = "N/A"
                        rating_el = card.locator("span.kvMYJc, div.Uy7F9, span.hCCjke")
                        if await rating_el.count() > 0:
                            aria = await rating_el.first.get_attribute("aria-label")
                            if aria:
                                match = re.search(r'(\d+\.?\d*)', aria)
                                rating = match.group(1) if match else "N/A"

                        text_el = card.locator("span.wiI7pd, div.jftiEf span, div.fontBodyMedium span")
                        review_text = ""
                        if await text_el.count() > 0:
                            review_text = (await text_el.first.inner_text()).strip()

                        reviews_data.append({
                            "review_id": review_id,
                            "author": author,
                            "rating": rating,
                            "text": review_text,
                            "scraped_at": datetime.utcnow().isoformat()
                        })

                        visited_ids.add(review_id)
                        new_found = True

                    except Exception:
                        continue

                if not new_found and len(reviews_data) > 5:
                    break

                try:
                    panel = page.locator("div[role='list']").first
                    await page.evaluate("el => el.scrollTop = el.scrollHeight", await panel.element_handle())
                except:
                    await page.mouse.wheel(0, 2500)

                await asyncio.sleep(random.uniform(2.5, 4.5))
                scroll_attempts += 1

        except Exception as e:
            logger.error(f"❌ Scraper error: {str(e)}")

        finally:
            await browser.close()

    logger.info(f"✅ Done: {len(reviews_data)} reviews")
    return reviews_data[:limit]


# =================================================================
# ALIAS
# =================================================================
scrape_google_reviews = fetch_reviews
