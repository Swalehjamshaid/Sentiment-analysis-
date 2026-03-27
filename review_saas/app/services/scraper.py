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
# BEST PRACTICE CONFIGURATION
# =================================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("ReviewSaaS.Scraper")

API_TOKEN = os.getenv("SCRAPE_DO_TOKEN")
if not API_TOKEN:
    logger.error("❌ SCRAPE_DO_TOKEN environment variable is required!")

# Limit concurrency to avoid burning free/paid credits quickly
sem = asyncio.Semaphore(4)  # Conservative for Scrape.do Free tier


async def fetch_reviews(
    place_id: str,
    limit: int = 20,
    sort_newest: bool = True,
    take_screenshot_on_zero: bool = False
):
    """
    World Best-Practice Google Maps Reviews Scraper using Scrape.do + Playwright (2026)
    - Hybrid: Network + DOM extraction
    - Robust Reviews tab + Sort handling
    - Human-like interaction
    """
    async with sem:
        logger.info(f"🚀 [Best Practice] Scraping reviews for place_id: {place_id} | Limit: {limit}")

        reviews_data = []
        visited_ids = set()

        # Direct Place URL (more stable than search URL)
        target_url = f"https://www.google.com/maps/place/?q=place_id:{place_id}"
        encoded_url = urllib.parse.quote(target_url)
        scrape_do_url = f"https://api.scrape.do?token={API_TOKEN}&url={encoded_url}&render=true"

        async with async_playwright() as p:
            try:
                browser = await p.chromium.launch(
                    headless=True,
                    args=[
                        "--no-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-blink-features=AutomationControlled",
                        "--disable-features=IsolateOrigins,site-per-process"
                    ]
                )

                context = await browser.new_context(
                    viewport={"width": 1366, "height": 950},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                               "(KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"
                )
                page = await context.new_page()
                await stealth_async(page)

                # ====================== NETWORK INTERCEPTION (Primary Method) ======================
                async def handle_batchexecute(response):
                    if len(reviews_data) >= limit or "batchexecute" not in response.url:
                        return
                    try:
                        text = await response.text()
                        cleaned = re.sub(r'^\)]}''\n?', '', text).strip()
                        matches = re.findall(r'\["wrb\.fr".*?\]\]', cleaned, re.DOTALL)

                        for match in matches:
                            try:
                                parsed = json.loads(match)
                                if len(parsed) < 3:
                                    continue
                                data = json.loads(parsed[2])

                                for block in data:
                                    if not isinstance(block, list):
                                        continue
                                    for item in block:
                                        if not isinstance(item, list) or len(item) < 5:
                                            continue

                                        review_id = str(item[0])
                                        if review_id in visited_ids or len(reviews_data) >= limit:
                                            continue

                                        author = item[1][0] if isinstance(item[1], (list, tuple)) and item[1] else "Anonymous"
                                        rating = item[4] if len(item) > 4 else None
                                        text_content = item[3] if len(item) > 3 else None

                                        review = {
                                            "review_id": review_id,
                                            "author_name": author,
                                            "rating": float(rating) if rating is not None else None,
                                            "text": str(text_content) if text_content else "No review text",
                                            "scraped_at": datetime.utcnow().isoformat()
                                        }
                                        reviews_data.append(review)
                                        visited_ids.add(review_id)
                                        logger.info(f"✅ Network: {len(reviews_data)}/{limit} - {author[:40]}")
                            except:
                                continue
                    except Exception:
                        pass

                page.on("response", handle_batchexecute)

                # ====================== NAVIGATION ======================
                logger.info("📡 Loading page via Scrape.do render=true...")
                await page.goto(scrape_do_url, wait_until="domcontentloaded", timeout=120000)
                await page.wait_for_timeout(12000)  # Allow heavy JS to settle

                # ====================== OPEN REVIEWS TAB (Multi-strategy) ======================
                logger.info("🖱️ Detecting and clicking Reviews tab...")
                tab_selectors = [
                    'button[aria-label*="Reviews"]',
                    'button[aria-label*="ریویوز"]',
                    'button:has-text("Reviews")',
                    'button:has-text("ریویوز")',
                    'div[role="tab"]:has-text("Reviews")',
                    '[data-value="Reviews"]',
                    '.hh2p_e',
                    'button[jsaction*="review"]'
                ]

                clicked = False
                for selector in tab_selectors:
                    try:
                        btn = page.locator(selector).first
                        if await btn.is_visible(timeout=6000):
                            await btn.scroll_into_view_if_needed()
                            await btn.click(force=True)
                            logger.info(f"✅ Reviews tab opened using: {selector}")
                            clicked = True
                            await page.wait_for_timeout(5000)
                            break
                    except:
                        continue

                if not clicked:
                    logger.warning("⚠️ Could not click Reviews tab. Proceeding with fallback scroll.")

                # ====================== SORT BY NEWEST (Best for Fresh Data) ======================
                if sort_newest:
                    try:
                        await page.wait_for_timeout(3000)
                        await page.locator('button:has-text("Sort")').first.click()
                        await page.wait_for_timeout(1500)
                        await page.locator('span:has-text("Newest")').first.click()
                        logger.info("✅ Sorted reviews by Newest")
                        await page.wait_for_timeout(4000)
                    except Exception:
                        logger.warning("Could not sort by Newest")

                # ====================== SCROLL + DOM EXTRACTION (Reliable Fallback) ======================
                logger.info("🔄 Smart scrolling + DOM extraction...")

                # Click "See more" for full review text
                async def expand_reviews():
                    try:
                        more_btns = page.locator('.w8nwRe, .kyuRq')
                        for i in range(await more_btns.count()):
                            if i >= 10: break
                            await more_btns.nth(i).click(force=True)
                            await asyncio.sleep(0.3)
                    except:
                        pass

                last_height = 0
                attempts = 0
                max_attempts = 18

                while len(reviews_data) < limit and attempts < max_attempts:
                    attempts += 1

                    # Human-like behavior
                    await page.mouse.move(random.randint(400, 900), random.randint(300, 700))
                    await page.mouse.wheel(0, random.randint(2800, 4800))
                    await asyncio.sleep(random.uniform(5.8, 9.5))

                    await expand_reviews()

                    # DOM Fallback Extraction (very stable in 2026)
                    try:
                        review_cards = page.locator('.jftiEf, [data-review-id]')
                        cards = await review_cards.all()
                        for card in cards:
                            try:
                                rid = await card.get_attribute("data-review-id")
                                if not rid or rid in visited_ids:
                                    continue

                                author_el = card.locator('.d4r55, .fontTitleSmall').first
                                author = (await author_el.text_content(timeout=2000) or "Anonymous").strip()

                                rating_el = card.locator('span[aria-label*="star"]').first
                                rating_text = await rating_el.get_attribute("aria-label", timeout=2000)
                                rating = float(rating_text.split()[0]) if rating_text else None

                                text_el = card.locator('.wiI7pd').first
                                text = (await text_el.text_content(timeout=3000) or "No text").strip()

                                review = {
                                    "review_id": rid,
                                    "author_name": author,
                                    "rating": rating,
                                    "text": text,
                                    "scraped_at": datetime.utcnow().isoformat()
                                }
                                reviews_data.append(review)
                                visited_ids.add(rid)
                                logger.info(f"✅ DOM: {len(reviews_data)}/{limit} - {author[:40]}")
                            except:
                                continue
                    except:
                        pass

                    # Stop if no new content
                    current_height = await page.evaluate("document.documentElement.scrollHeight")
                    if current_height == last_height and len(reviews_data) >= 5:
                        break
                    last_height = current_height

                logger.info(f"🏁 Scraping finished. Total reviews: {len(reviews_data)}")

                if len(reviews_data) == 0 and take_screenshot_on_zero:
                    await page.screenshot(path=f"debug_zero_reviews_{place_id[:12]}.png")
                    logger.info("📸 Screenshot saved for debugging (zero reviews)")

            except Exception as e:
                logger.error(f"❌ Critical error during scraping: {str(e)}", exc_info=True)
            finally:
                await browser.close()

        return reviews_data[:limit]


# =================================================================
# Aliases for easy integration
# =================================================================
scrape_google_reviews = fetch_reviews
run_scraper = fetch_reviews
