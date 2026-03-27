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
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("ReviewSaaS.Scraper")

# Credentials from Railway Environment Variables
API_TOKEN = os.getenv("SCRAPE_DO_TOKEN")

# Scrape.do Free Plan limit
sem = asyncio.Semaphore(5)

# =================================================================
# CORE SCRAPER FUNCTION
# =================================================================
async def fetch_reviews(place_id: str, limit: int = 50):
    """
    Complete Intercept-and-Scroll Scraper.
    Logic: 
    1. Call Scrape.do API Gateway.
    2. 'Listen' for internal Google data (BatchExecute).
    3. Physically scroll the page to trigger data loading.
    4. Parse and return the intercepted JSON.
    """
    async with sem:
        logger.info(f"🚀 [Railway] Initializing Master Scraper for: {place_id}")
        
        if not API_TOKEN:
            logger.error("❌ SCRAPE_DO_TOKEN missing in Railway Variables!")
            return []

        reviews_data = []
        visited_ids = set()

        # Google Maps URL Format
        target_url = f"https://www.google.com/maps/search/?api=1&query=Google&query_place_id={place_id}"
        encoded_url = urllib.parse.quote(target_url)
        
        # Scrape.do Gateway (render=true is mandatory for JS interception)
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

                # --- THE INTERCEPTION LOGIC (The "Video" Method) ---
                async def handle_response(response):
                    # We only care about the background data stream from Google
                    if "batchexecute" in response.url:
                        try:
                            text = await response.text()
                            # Clean Google's security prefix
                            cleaned = text.replace(")]}'", "").strip()
                            matches = re.findall(r'\["wrb\.fr".*?\]\]', cleaned)
                            
                            for match in matches:
                                # Convert string match to actual Python list
                                inner = json.loads(json.loads(match)[2])
                                for block in [b for b in inner if isinstance(b, list)]:
                                    for r in block:
                                        try:
                                            # Indexing based on Google's internal JSON structure
                                            r_id = r[0]
                                            if r_id not in visited_ids:
                                                reviews_data.append({
                                                    "review_id": r_id,
                                                    "author_name": r[1][0],
                                                    "rating": r[4],
                                                    "text": r[3] or "",
                                                    "relative_date": r[1][4],
                                                    "scraped_at": datetime.utcnow().isoformat()
                                                })
                                                visited_ids.add(r_id)
                                        except (IndexError, TypeError): continue
                        except: pass

                # Tell Playwright to start 'listening'
                page.on("response", handle_response)

                logger.info("📡 Navigating via Scrape.do API...")
                # We use 'load' to ensure the basic structure is there before we start scrolling
                await page.goto(scrape_do_gateway, wait_until="load", timeout=120000)

                # --- THE SCROLLING LOGIC ---
                # We need to find the review panel and scroll it to trigger 'batchexecute'
                logger.info("⏳ Attempting to locate review panel and scroll...")
                
                # Wait for the main content to load
                await page.wait_for_timeout(5000)

                # Find the scrollable container (Google uses different classes, 
                # but 'role=main' or specific mouse-wheel actions usually work)
                for i in range((limit // 5) + 5):
                    if len(reviews_data) >= limit: break
                    
                    # Method: Mouse Wheel Scroll
                    await page.mouse.wheel(0, 4000)
                    
                    # Random wait to allow the API to fetch next batch
                    await asyncio.sleep(random.uniform(4, 6))
                    
                    if len(reviews_data) > 0:
                        logger.info(f"📊 Captured {len(reviews_data)} reviews so far...")

            except Exception as e:
                logger.error(f"❌ Scraper failure: {str(e)}")
            finally:
                await browser.close()
                logger.info(f"✅ Finished. Total Intercepted: {len(reviews_data)}")

    return reviews_data[:limit]

# Aliases for your ReviewSaaS logic
scrape_google_reviews = fetch_reviews
run_scraper = fetch_reviews
