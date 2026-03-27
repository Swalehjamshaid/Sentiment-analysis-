import asyncio
import json
import re
import random
import logging
import os
import urllib.parse
from datetime import datetime
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

# =================================================================
# CONFIGURATION & LOGGING
# =================================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("ReviewSaaS.Scraper")

# Pull token from Railway Environment Variable
API_TOKEN = os.getenv("SCRAPE_DO_TOKEN")

# Concurrency limit (Free plan of Scrape.do is quite restrictive)
sem = asyncio.Semaphore(5)


# =================================================================
# CORE SCRAPER FUNCTION (Updated 2026)
# =================================================================
async def fetch_reviews(place_id: str, limit: int = 5):
    """
    Improved Google Maps Reviews Scraper via Scrape.do
    - Uses Scrape.do render=true as proxy/gateway
    - Robust Reviews tab detection (multi-language support)
    - Enhanced batchexecute interception
    """
    async with sem:
        logger.info(f"🚀 Starting review scraper for place_id: {place_id} | Limit: {limit}")

        if not API_TOKEN:
            logger.error("❌ SCRAPE_DO_TOKEN environment variable is missing!")
            return []

        reviews_data = []
        visited_ids = set()

        # Target Google Maps URL
        target_url = f"https://www.google.com/maps/search/?api=1&query=Google&query_place_id={place_id}"
        encoded_url = urllib.parse.quote(target_url)

        # Scrape.do Gateway
        scrape_do_gateway = f"https://api.scrape.do?token={API_TOKEN}&url={encoded_url}&render=true"

        async with async_playwright() as p:
            try:
                browser = await p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"]
                )
                context = await browser.new_context(
                    viewport={'width': 1280, 'height': 900},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"
                )
                page = await context.new_page()
                await stealth_async(page)

                # ====================== NETWORK INTERCEPTION ======================
                async def handle_response(response):
                    if len(reviews_data) >= limit:
                        return
                    if "batchexecute" not in response.url:
                        return

                    try:
                        text = await response.text()
                        # Clean the weird Google prefix
                        cleaned = re.sub(r'^\)]}''\n?', '', text).strip()

                        # Find all wrb.fr blocks
                        matches = re.findall(r'\["wrb\.fr".*?\]\]', cleaned, re.DOTALL)
                        for match in matches:
                            try:
                                # Double JSON decode is common with Google
                                data = json.loads(json.loads(match)[2])
                                for block in data:
                                    if not isinstance(block, list):
                                        continue
                                    for item in block:
                                        if not isinstance(item, list) or len(item) < 5:
                                            continue

                                        review_id = item[0]
                                        if review_id in visited_ids or len(reviews_data) >= limit:
                                            continue

                                        author = item[1][0] if isinstance(item[1], list) and item[1] else "Anonymous"
                                        rating = item[4] if len(item) > 4 else None
                                        text_content = item[3] if len(item) > 3 else None

                                        review = {
                                            "review_id": review_id,
                                            "author_name": author,
                                            "rating": float(rating) if rating is not None else None,
                                            "text": text_content or "No review text provided",
                                            "scraped_at": datetime.utcnow().isoformat()
                                        }
                                        reviews_data.append(review)
                                        visited_ids.add(review_id)
                                        logger.info(f"✅ Captured review {len(reviews_data)}/{limit} by {author}")
                            except Exception as inner_e:
                                continue
                    except Exception as e:
                        pass  # Silent fail on malformed packets

                page.on("response", handle_response)

                # ====================== NAVIGATION ======================
                logger.info("📡 Navigating via Scrape.do...")
                await page.goto(scrape_do_gateway, wait_until="domcontentloaded", timeout=120000)
                await page.wait_for_timeout(8000)  # Let Maps JS settle

                # ====================== UNIVERSAL REVIEWS TAB CLICK ======================
                logger.info("🖱️ Hunting for the Reviews tab...")

                tab_selectors = [
                    'button[aria-label*="Reviews"]',
                    'button[aria-label*="ریویوز"]',      # Urdu
                    'button[aria-label*="ریویو"]',
                    'button:has-text("Reviews")',
                    'button:has-text("ریویوز")',
                    'div[role="tab"]:has-text("Reviews")',
                    'div[role="tab"]:has-text("ریویوز")',
                    '.hh2p_e',           # Common internal class
                    '[data-value="Reviews"]',
                    'button[jsaction*="review"]'
                ]

                clicked = False
                for selector in tab_selectors:
                    try:
                        btn = page.locator(selector).first
                        if await btn.count() > 0 and await btn.is_visible(timeout=4000):
                            await btn.click(force=True)
                            logger.info(f"✅ Clicked Reviews tab with selector: {selector}")
                            clicked = True
                            await page.wait_for_timeout(3000)
                            break
                    except Exception:
                        continue

                if not clicked:
                    logger.warning("⚠️ Could not reliably click Reviews tab. Proceeding with scroll anyway.")

                # ====================== SCROLLING TO LOAD REVIEWS ======================
                logger.info("🔄 Scrolling to load review batches...")
                scroll_attempts = 0
                max_scrolls = 8

                while len(reviews_data) < limit and scroll_attempts < max_scrolls:
                    scroll_attempts += 1

                    # Move mouse to review panel area
                    await page.mouse.move(600, 500)
                    await page.mouse.wheel(0, 3500)

                    await asyncio.sleep(random.uniform(4.5, 7.5))

                    # Occasional extra scroll + pause
                    if scroll_attempts % 3 == 0:
                        await page.mouse.wheel(0, 2000)
                        await page.wait_for_timeout(2000)

                logger.info(f"🏁 Scrolling finished. Found {len(reviews_data)} reviews.")

            except Exception as e:
                logger.error(f"❌ Critical scraper error: {str(e)}", exc_info=True)
            finally:
                await browser.close()
                logger.info(f"✅ Scraping session ended. Total reviews captured: {len(reviews_data)}")

        return reviews_data[:limit]


# Aliases for your app
scrape_google_reviews = fetch_reviews
run_scraper = fetch_reviews
