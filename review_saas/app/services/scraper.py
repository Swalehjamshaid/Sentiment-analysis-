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

API_TOKEN = os.getenv("SCRAPE_DO_TOKEN")
sem = asyncio.Semaphore(5)   # Keep low for Free tier


async def fetch_reviews(place_id: str, limit: int = 5):
    async with sem:
        logger.info(f"🚀 Starting improved scraper for place_id: {place_id} | Limit: {limit}")

        if not API_TOKEN:
            logger.error("❌ SCRAPE_DO_TOKEN is missing!")
            return []

        reviews_data = []
        visited_ids = set()

        target_url = f"https://www.google.com/maps/search/?api=1&query=Google&query_place_id={place_id}"
        encoded_url = urllib.parse.quote(target_url)
        scrape_do_gateway = f"https://api.scrape.do?token={API_TOKEN}&url={encoded_url}&render=true"

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
                    viewport={"width": 1366, "height": 900},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"
                )
                page = await context.new_page()
                await stealth_async(page)

                # ====================== IMPROVED NETWORK INTERCEPTION ======================
                async def handle_response(response):
                    if len(reviews_data) >= limit or "batchexecute" not in response.url:
                        return

                    try:
                        text = await response.text()
                        # Clean Google prefix
                        cleaned = re.sub(r'^\)]}''\n?', '', text).strip()

                        # Find wrb.fr blocks (more flexible regex)
                        matches = re.findall(r'\["wrb\.fr".*?\]\]', cleaned, re.DOTALL | re.MULTILINE)
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
                                            "rating": float(rating) if isinstance(rating, (int, float, str)) else None,
                                            "text": str(text_content) if text_content else "No review text",
                                            "scraped_at": datetime.utcnow().isoformat()
                                        }
                                        reviews_data.append(review)
                                        visited_ids.add(review_id)
                                        logger.info(f"✅ Captured {len(reviews_data)}/{limit}: {author[:30]}...")
                            except:
                                continue
                    except Exception:
                        pass

                page.on("response", handle_response)

                # ====================== NAVIGATION ======================
                logger.info("📡 Navigating via Scrape.do...")
                await page.goto(scrape_do_gateway, wait_until="domcontentloaded", timeout=120_000)
                await page.wait_for_timeout(10_000)   # Longer initial wait for heavy JS

                # ====================== ROBUST REVIEWS TAB CLICK ======================
                logger.info("🖱️ Hunting for Reviews tab (2026 updated selectors)...")

                tab_selectors = [
                    'button[aria-label*="Reviews"]',
                    'button[aria-label*="ریویوز"]',
                    'button[aria-label*="ریویو"]',
                    'button:has-text("Reviews")',
                    'button:has-text("ریویوز")',
                    'div[role="tab"]:has-text("Reviews")',
                    'div[role="tab"]:has-text("ریویوز")',
                    '[data-value="Reviews"]',
                    'button[jsaction*="review"]',
                    '.hh2p_e',                    # still appears sometimes
                    'span:has-text("Reviews") >> xpath=ancestor::button'
                ]

                clicked = False
                for sel in tab_selectors:
                    try:
                        btn = page.locator(sel).first
                        if await btn.is_visible(timeout=5000):
                            await btn.scroll_into_view_if_needed()
                            await btn.click(force=True)
                            logger.info(f"✅ Clicked Reviews tab using: {sel}")
                            clicked = True
                            await page.wait_for_timeout(4000)
                            break
                    except Exception:
                        continue

                if not clicked:
                    logger.warning("⚠️ Tab click failed. Trying fallback: click on any tab panel or 'Sort by'")
                    # Fallback: click anywhere in the tab area or "Sort by" button
                    try:
                        await page.locator('button:has-text("Sort")').first.click(timeout=5000)
                        await page.wait_for_timeout(2000)
                    except:
                        pass

                # ====================== SCROLLING + WAIT FOR REVIEWS ======================
                logger.info("🔄 Aggressive scrolling to trigger review batches...")

                # Wait for review container as fallback
                try:
                    await page.wait_for_selector('div.jftiEf, div[data-review-id]', timeout=8000)
                    logger.info("✅ Review elements detected on page")
                except:
                    logger.warning("No review DOM elements found yet")

                scroll_attempts = 0
                max_attempts = 12

                while len(reviews_data) < limit and scroll_attempts < max_attempts:
                    scroll_attempts += 1

                    # Move mouse to likely sidebar area
                    await page.mouse.move(random.randint(500, 700), random.randint(300, 600))
                    await page.mouse.wheel(0, random.randint(2800, 4200))

                    await asyncio.sleep(random.uniform(5.0, 8.5))

                    # Extra scroll every 3 attempts
                    if scroll_attempts % 3 == 0:
                        await page.mouse.wheel(0, 1500)
                        await page.wait_for_timeout(2500)

                logger.info(f"🏁 Scrolling complete. Captured: {len(reviews_data)} reviews")

                # Optional debug: take screenshot if zero reviews
                # if len(reviews_data) == 0:
                #     await page.screenshot(path=f"debug_{place_id[:10]}.png")
                #     logger.info("📸 Screenshot saved for debugging")

            except Exception as e:
                logger.error(f"❌ Scraper error: {str(e)}", exc_info=True)
            finally:
                await browser.close()
                logger.info(f"✅ Session ended. Total reviews: {len(reviews_data)}")

        return reviews_data[:limit]


# Aliases
scrape_google_reviews = fetch_reviews
run_scraper = fetch_reviews
