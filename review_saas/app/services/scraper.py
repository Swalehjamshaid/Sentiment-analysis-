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

# Limit concurrency to 5 as per Scrape.do Free Plan
sem = asyncio.Semaphore(5)

# =================================================================
# CORE SCRAPER FUNCTION
# =================================================================
async def fetch_reviews(place_id: str, limit: int = 5):
    """
    Complete Scraper: 
    - API Gateway via Scrape.do
    - Tab Switching (Overview -> Reviews)
    - Network Interception (BatchExecute)
    - Stops at exactly 5 reviews.
    """
    async with sem:
        logger.info(f"🚀 [Railway] Starting 5-Review Scraper for: {place_id}")
        
        if not API_TOKEN:
            logger.error("❌ SCRAPE_DO_TOKEN missing in Railway Variables!")
            return []

        reviews_data = []
        visited_ids = set()

        # Target Google Maps URL
        target_url = f"https://www.google.com/maps/search/?api=1&query=Google&query_place_id={place_id}"
        encoded_url = urllib.parse.quote(target_url)
        
        # Scrape.do Gateway URL with JS Rendering enabled
        scrape_do_gateway = f"https://api.scrape.do?token={API_TOKEN}&url={encoded_url}&render=true"

        async with async_playwright() as p:
            try:
                browser = await p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-dev-shm-usage"]
                )
                context = await browser.new_context(viewport={'width': 1280, 'height': 800})
                page = await context.new_page()
                await stealth_async(page)

                # --- NETWORK INTERCEPTION LOGIC ---
                async def handle_response(response):
                    # Stop if we already hit our 5-review limit
                    if len(reviews_data) >= limit:
                        return

                    if "batchexecute" in response.url:
                        try:
                            text = await response.text()
                            cleaned = text.replace(")]}'", "").strip()
                            matches = re.findall(r'\["wrb\.fr".*?\]\]', cleaned)
                            
                            for match in matches:
                                inner = json.loads(json.loads(match)[2])
                                for block in [b for b in inner if isinstance(b, list)]:
                                    for r in block:
                                        try:
                                            r_id = r[0]
                                            if r_id not in visited_ids and len(reviews_data) < limit:
                                                reviews_data.append({
                                                    "review_id": r_id,
                                                    "author_name": r[1][0],
                                                    "rating": r[4],
                                                    "text": r[3] or "No text content",
                                                    "scraped_at": datetime.utcnow().isoformat()
                                                })
                                                visited_ids.add(r_id)
                                                logger.info(f"✨ Captured Review {len(reviews_data)}: {r[1][0]}")
                                        except: continue
                        except: pass

                page.on("response", handle_response)

                # --- EXECUTION ---
                logger.info("📡 Navigating via Scrape.do API Gateway...")
                await page.goto(scrape_do_gateway, wait_until="load", timeout=120000)
                
                # Give the page a moment to load the sidebar
                await page.wait_for_timeout(5000)

                # TRIGGER: Click the "Reviews" tab to start the data flow
                logger.info("🖱️ Attempting to click Reviews tab...")
                try:
                    # Look for the button that contains the word "Reviews"
                    review_tab = page.locator('button[aria-label*="Reviews"]').first
                    await review_tab.click()
                    await page.wait_for_timeout(3000)
                except Exception as e:
                    logger.warning(f"⚠️ Could not click Reviews tab automatically: {e}")

                # SCROLLING: Just a few scrolls needed for 5 reviews
                logger.info("🔄 Scrolling to trigger data packets...")
                for i in range(3):
                    if len(reviews_data) >= limit:
                        break
                    
                    # Scroll down
                    await page.mouse.wheel(0, 2000)
                    await asyncio.sleep(random.uniform(4, 6))

            except Exception as e:
                logger.error(f"❌ Scraper failure: {str(e)}")
            finally:
                await browser.close()
                logger.info(f"✅ Scraping Complete. Total Found: {len(reviews_data)}")

        return reviews_data[:limit]

# Aliases for app integration
scrape_google_reviews = fetch_reviews
run_scraper = fetch_reviews
