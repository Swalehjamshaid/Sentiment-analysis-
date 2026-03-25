import asyncio
import json
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
# SCRAPING ENGINE (PLAYWRIGHT ASYNC) - Updated with Video Logic
# =================================================================
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

async def fetch_reviews(place_id: str, limit: int = 50):
    """
    Core function to scrape Google Reviews using video tutorial logic.
    Uses DOM selectors + scrolling + "More" button clicks + deduplication.
    """
    logger.info(f"🚀 Starting scraper for Place ID: {place_id} | Limit: {limit}")

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
            # Go to Google Maps with English
            url = f"https://www.google.com/maps/place/?q=place_id:{place_id}&hl=en"
            await page.goto(url, wait_until="networkidle", timeout=60000)

            # Click "Reviews" tab
            await page.locator('button[aria-label*="Reviews for"]').click(timeout=10000)
            await asyncio.sleep(4)

            logger.info("Starting scroll + expand loop...")

            scroll_attempts = 0
            max_attempts = (limit // 8) + 10

            while len(reviews_data) < limit and scroll_attempts < max_attempts:
                # Expand all "More" buttons
                more_buttons = page.locator("button.w8nwRe.kyuRq")
                if await more_buttons.count() > 0:
                    for btn in await more_buttons.all():
                        try:
                            await btn.click(timeout=2000)
                        except:
                            pass
                    await asyncio.sleep(1.5)

                # Extract currently visible reviews
                review_cards = page.locator("div.jJc9Ad")
                cards = await review_cards.all()

                new_found = False
                for card in cards:
                    try:
                        # Unique review ID
                        review_id = await card.get_attribute("data-review-id")
                        if not review_id:
                            review_id = "temp_" + str(hash(await card.inner_text()))
                        if review_id in visited_ids:
                            continue

                        author = await card.locator("div.d4r55").inner_text(timeout=3000)

                        # Rating (primary method)
                        rating_el = card.locator("span.kvMYJc")
                        if await rating_el.count() > 0:
                            aria_label = await rating_el.first.get_attribute("aria-label")
                            rating = re.sub(r'\D', '', aria_label) if aria_label else "N/A"
                        else:
                            # Fallback for star icons
                            alt_el = card.locator("span.fzvQib")
                            rating_text = await alt_el.first.inner_text() if await alt_el.count() > 0 else ""
                            match = re.search(r'(\d+\.?\d*)/5', rating_text)
                            rating = match.group(1) if match else "N/A"

                        text_el = card.locator("span.wiI7pd")
                        review_text = await text_el.inner_text(timeout=5000) if await text_el.count() > 0 else ""

                        reviews_data.append({
                            "review_id": review_id,
                            "author": author.strip(),
                            "rating": rating,
                            "text": review_text.strip(),
                            "scraped_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        })
                        visited_ids.add(review_id)
                        new_found = True

                    except Exception:
                        continue  # Skip problematic cards

                if not new_found:
                    logger.info("No new reviews found – stopping early.")
                    break

                # Scroll down
                await page.mouse.wheel(0, 3000)
                await asyncio.sleep(random.uniform(2.5, 4.8))

                scroll_attempts += 1
                logger.info(f"Progress: {len(reviews_data)} / {limit} reviews collected")

        except Exception as e:
            logger.error(f"❌ Critical error: {str(e)}")

        finally:
            await browser.close()

    logger.info(f"✅ Scraping finished. Total reviews: {len(reviews_data)}")
    return reviews_data[:limit]


# =================================================================
# COMPATIBILITY ALIAS & EXPORT
# =================================================================
scrape_google_reviews = fetch_reviews


def save_results_to_csv(data, filename="scraped_reviews.csv"):
    """Saves the extracted dictionary list to a local CSV file."""
    if not data:
        print("No data found to save.")
        return

    keys = data[0].keys()
    with open(filename, 'w', newline='', encoding='utf-8') as output_file:
        dict_writer = csv.DictWriter(output_file, fieldnames=keys)
        dict_writer.writeheader()
        dict_writer.writerows(data)
    print(f"📁 Data exported successfully to {filename}")


# =================================================================
# TEST EXECUTION
# =================================================================
if __name__ == "__main__":
    # Test using a known Place ID (Sydney Opera House example)
    SAMPLE_PLACE_ID = "ChIJN1t_tDeuEmsRUoG3yEAt848"

    final_output = asyncio.run(fetch_reviews(SAMPLE_PLACE_ID, limit=30))
    save_results_to_csv(final_output)
