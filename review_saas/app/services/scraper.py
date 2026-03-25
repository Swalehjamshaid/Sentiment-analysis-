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
# PLAYWRIGHT (CHROMIUM ONLY)
# =================================================================
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async


async def fetch_reviews(place_id: str, limit: int = 50):
    logger.info(f"🚀 Starting scraper for Place ID: {place_id} | Target: {limit}")

    reviews_data = []
    visited_ids = set()

    async with async_playwright() as p:

        # ==========================================================
        # 🔥 FIX 1: USE CHROMIUM (NOT FIREFOX)
        # ==========================================================
        try:
            selected_proxy = random.choice(PROXIES)

            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled"
                ],
                proxy={"server": selected_proxy}
            )
        except Exception:
            logger.warning("⚠️ Proxy failed, launching without proxy...")
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled"
                ]
            )

        context = await browser.new_context(
            viewport={"width": 1280, "height": 1280},
            locale="en-US",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
            extra_http_headers={"Accept-Language": "en-US,en;q=0.9"}
        )

        page = await context.new_page()
        await stealth_async(page)

        try:
            url = f"https://www.google.com/maps/place/?q=place_id:{place_id}&hl=en"
            await page.goto(url, wait_until="networkidle", timeout=90000)

            # ======================================================
            # CLICK REVIEWS BUTTON
            # ======================================================
            await page.locator('button[aria-label*="Reviews"]').click(timeout=15000)
            await asyncio.sleep(random.uniform(3, 5))

            logger.info("Starting scroll + expand loop...")

            scroll_attempts = 0
            max_attempts = (limit // 10) + 15

            while len(reviews_data) < limit and scroll_attempts < max_attempts:

                # ==================================================
                # EXPAND "MORE" BUTTONS
                # ==================================================
                more_buttons = page.locator("button.w8nwRe")
                count = await more_buttons.count()

                for i in range(count):
                    try:
                        await more_buttons.nth(i).click(timeout=2000)
                    except:
                        pass

                # ==================================================
                # EXTRACT REVIEWS
                # ==================================================
                review_cards = page.locator("div.jftiEf")
                cards = await review_cards.all()

                new_found = False

                for card in cards:
                    try:
                        review_id = await card.get_attribute("data-review-id")
                        if not review_id or review_id in visited_ids:
                            continue

                        # AUTHOR
                        author = "N/A"
                        author_el = card.locator(".d4r55")
                        if await author_el.count() > 0:
                            author = (await author_el.first.inner_text()).strip()

                        # RATING
                        rating = 0
                        rating_el = card.locator("span.kvMYJc")
                        if await rating_el.count() > 0:
                            aria = await rating_el.first.get_attribute("aria-label")
                            if aria:
                                match = re.search(r'(\d+)', aria)
                                rating = int(match.group(1)) if match else 0

                        # TEXT
                        text = ""
                        text_el = card.locator("span.wiI7pd")
                        if await text_el.count() > 0:
                            text = (await text_el.first.inner_text()).strip()

                        reviews_data.append({
                            "review_id": review_id,
                            "author_name": author,   # ✅ aligned with your API
                            "rating": rating,
                            "text": text,
                            "scraped_at": datetime.utcnow().isoformat()
                        })

                        visited_ids.add(review_id)
                        new_found = True

                    except:
                        continue

                if not new_found and len(reviews_data) > 5:
                    logger.info("No new reviews → stopping early")
                    break

                # ==================================================
                # SCROLL PANEL
                # ==================================================
                try:
                    await page.mouse.wheel(0, 3000)
                except:
                    pass

                await asyncio.sleep(random.uniform(2.5, 4.5))
                scroll_attempts += 1

                logger.info(f"Progress: {len(reviews_data)}/{limit}")

        except Exception as e:
            logger.error(f"❌ Scraper error: {str(e)}")

        finally:
            await browser.close()

    logger.info(f"✅ Finished. Collected {len(reviews_data)} reviews.")
    return reviews_data[:limit]


# =================================================================
# EXPORTS (DO NOT CHANGE)
# =================================================================
scrape_google_reviews = fetch_reviews


def save_results_to_csv(data, filename="scraped_reviews.csv"):
    if not data:
        print("No data found.")
        return

    keys = data[0].keys()
    with open(filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(data)

    print(f"📁 Saved to {filename}")


# =================================================================
# LOCAL TEST
# =================================================================
if __name__ == "__main__":
    SAMPLE_PLACE_ID = "ChIJN1t_tDeuEmsRUoG3yEAt848"
    output = asyncio.run(fetch_reviews(SAMPLE_PLACE_ID, limit=30))
    save_results_to_csv(output)
