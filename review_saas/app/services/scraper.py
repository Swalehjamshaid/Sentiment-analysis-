import asyncio
import re
import random
import logging
import csv
from datetime import datetime

# =================================================================
# GLOBAL CONFIGURATION & LOGGING
# =================================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("ReviewSaaS.Scraper")

# =================================================================
# RESIDENTIAL PROXY POOL (Smartproxy / Decodo)
# =================================================================
PROXIES = [
    "http://dkgjitgr:uzeqkqwjwmqe@31.59.20.176:6754",
    "http://dkgjitgr:uzeqkqwjwmqe@23.95.150.145:6114",
    "http://dkgjitgr:uzeqkqwjwmqe@198.23.239.134:6540",
    "http://dkgjitgr:uzeqkqwjwmqe@45.38.107.97:6014",
    "http://dkgjitgr:uzeqkqwjwmqe@107.172.163.27:6543"
]

# =================================================================
# SCRAPING ENGINE (PLAYWRIGHT ASYNC) - 2026 Updated Logic
# =================================================================
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

async def fetch_reviews(place_id: str, limit: int = 50):
    """
    Reliable Google Maps Reviews Scraper (2026 version).
    Uses DOM extraction with fallback selectors from recent tutorials.
    """
    logger.info(f"🚀 Starting scraper for Place ID: {place_id} | Target: {limit} reviews")

    reviews_data = []
    visited_ids = set()
    selected_proxy = random.choice(PROXIES)

    async with async_playwright() as p:
        browser = await p.firefox.launch(
            headless=True,
            proxy={"server": selected_proxy}
        )

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

            # Click Reviews tab (very stable selector)
            await page.locator('button[aria-label*="Reviews for"]').click(timeout=15000)
            await asyncio.sleep(random.uniform(3, 5))

            logger.info("Starting scroll + expand loop...")

            scroll_attempts = 0
            max_attempts = (limit // 10) + 15

            while len(reviews_data) < limit and scroll_attempts < max_attempts:
                # 1. Expand ALL "More" buttons (most important for full text)
                more_buttons = page.locator("button.w8nwRe.kyuRq, button[data-review-id] button")
                count = await more_buttons.count()
                if count > 0:
                    logger.info(f"Expanding {count} 'More' buttons...")
                    for btn in await more_buttons.all():
                        try:
                            await btn.click(timeout=3000)
                            await asyncio.sleep(0.3)
                        except:
                            pass
                    await asyncio.sleep(2)

                # 2. Extract reviews with multiple fallback selectors (2025–2026 common classes)
                review_cards = page.locator("div.jJc9Ad, div.jftiEf, div[data-review-id]")
                cards = await review_cards.all()

                new_found = False
                for card in cards:
                    try:
                        # Unique ID
                        review_id = await card.get_attribute("data-review-id") or f"rev_{len(reviews_data)}"
                        if review_id in visited_ids:
                            continue

                        # Author
                        author = "N/A"
                        author_el = card.locator("div.d4r55, span.X43Kjb, div.fontBodyMedium")
                        if await author_el.count() > 0:
                            author = (await author_el.first.inner_text(timeout=3000)).strip()

                        # Rating with multiple fallbacks
                        rating = "N/A"
                        rating_el = card.locator("span.kvMYJc, div.Uy7F9, span.hCCjke")
                        if await rating_el.count() > 0:
                            aria = await rating_el.first.get_attribute("aria-label")
                            if aria:
                                match = re.search(r'(\d+\.?\d*)', aria)
                                rating = match.group(1) if match else "N/A"

                        # Review text (full after "More")
                        text_el = card.locator("span.wiI7pd, div.jftiEf span, div.fontBodyMedium span")
                        review_text = ""
                        if await text_el.count() > 0:
                            review_text = (await text_el.first.inner_text(timeout=5000)).strip()

                        reviews_data.append({
                            "review_id": review_id,
                            "author": author,
                            "rating": rating,
                            "text": review_text,
                            "scraped_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        })
                        visited_ids.add(review_id)
                        new_found = True

                    except Exception:
                        continue

                if not new_found and len(reviews_data) > 5:
                    logger.info("No new reviews loaded – stopping early.")
                    break

                # 3. Scroll the review panel (more reliable than mouse wheel on whole page)
                try:
                    panel = page.locator("div.m6QErb.DxyBCb.kA9KIf.dS8AeF, div[role='list'], div.jJc9Ad").first
                    await panel.scroll_into_view_if_needed(timeout=5000)
                    await page.evaluate("el => el.scrollTop = el.scrollHeight", await panel.element_handle())
                except:
                    await page.mouse.wheel(0, 2500)  # fallback

                await asyncio.sleep(random.uniform(2.8, 5.2))
                scroll_attempts += 1
                logger.info(f"Progress: {len(reviews_data)} / {limit} reviews | Attempts: {scroll_attempts}")

        except Exception as e:
            logger.error(f"❌ Critical error during scraping: {str(e)}")

        finally:
            await browser.close()

    logger.info(f"✅ Finished. Collected {len(reviews_data)} reviews.")
    return reviews_data[:limit]


# =================================================================
# COMPATIBILITY ALIAS & EXPORT
# =================================================================
scrape_google_reviews = fetch_reviews


def save_results_to_csv(data, filename="scraped_reviews.csv"):
    if not data:
        print("No data found to save.")
        return
    keys = data[0].keys()
    with open(filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(data)
    print(f"📁 Data saved to {filename}")


# =================================================================
# TEST EXECUTION
# =================================================================
if __name__ == "__main__":
    SAMPLE_PLACE_ID = "ChIJN1t_tDeuEmsRUoG3yEAt848"  # Sydney Opera House example

    final_output = asyncio.run(fetch_reviews(SAMPLE_PLACE_ID, limit=30))
    save_results_to_csv(final_output)
