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

# This pulls the token from your Railway Environment Variable: SCRAPE_DO_TOKEN
# Make sure you have added this name and your token in the Railway Dashboard.
API_TOKEN = os.getenv("SCRAPE_DO_TOKEN")

# Scrape.do Free Plan has a limit of 5 concurrent requests.
# This Semaphore ensures your app never tries to run more than 5 at once.
sem = asyncio.Semaphore(5)

# =================================================================
# CORE SCRAPER FUNCTION
# =================================================================
async def fetch_reviews(place_id: str, limit: int = 50):
    """
    Railway-optimized scraper using Scrape.do API Gateway.
    This bypasses proxy tunnels by using a direct API request.
    """
    async with sem:  # Protects your 5-concurrency limit
        logger.info(f"🚀 [Railway] Starting Scrape.do Scraper for: {place_id}")
        
        if not API_TOKEN:
            logger.error("❌ SCRAPE_DO_TOKEN not found in Railway Variables! Check your dashboard.")
            return []

        reviews_data = []
        visited_ids = set()

        # 1. Target URL (The Google Maps Reviews page)
        # Using the 0{place_id} format to trigger the correct Google redirect
        target_url = f"https://www.google.com/maps/search/?api=1&query=Google&query_place_id={place_id}"
        
        # 2. URL Encoding (Crucial for API parameters)
        encoded_url = urllib.parse.quote(target_url)
        
        # 3. Build Scrape.do Gateway URL 
        # '&render=true' is required for Google Maps because it uses heavy JavaScript
        scrape_do_gateway = f"https://api.scrape.do?token={API_TOKEN}&url={encoded_url}&render=true"

        async with async_playwright() as p:
            try:
                # Launch WITHOUT proxy settings (the API handles proxies on its side)
                browser = await p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
                )
                context = await browser.new_context(
                    viewport={'width': 1280, 'height': 800}
                )
                page = await context.new_page()
                await stealth_async(page)

                # --- DATA INTERCEPTION LOGIC ---
                # We listen for the 'batchexecute' network response where Google sends review data
                async def handle_response(response):
                    if "batchexecute" in response.url:
                        try:
                            text = await response.text()
                            # Clean the Google-specific security prefix
                            cleaned = text.replace(")]}'", "").strip()
                            matches = re.findall(r'\["wrb\.fr".*?\]\]', cleaned)
                            for match in matches:
                                inner = json.loads(json.loads(match)[2])
                                for block in [b for b in inner if isinstance(b, list)]:
                                    for r in block:
                                        try:
                                            r_id = r[0]
                                            if r_id not in visited_ids:
                                                reviews_data.append({
                                                    "review_id": r_id,
                                                    "author_name": r[1][0],
                                                    "rating": r[4],
                                                    "text": r[3] or "",
                                                    "scraped_at": datetime.utcnow().isoformat()
                                                })
                                                visited_ids.add(r_id)
                                        except (IndexError, TypeError): 
                                            continue
                        except Exception: 
                            pass

                page.on("response", handle_response)

                logger.info("📡 Requesting page through Scrape.do API Gateway...")
                # We give the API 120 seconds to render the JavaScript and return the page
                await page.goto(scrape_do_gateway, wait_until="networkidle", timeout=120000)

                # --- SCROLLING TO FETCH MORE REVIEWS ---
                # This triggers more 'batchexecute' requests for the interceptor to catch
                for i in range((limit // 5) + 5):
                    if len(reviews_data) >= limit: 
                        break
                    
                    await page.mouse.wheel(0, 4000)
                    # Use a random sleep to mimic human behavior and avoid rate limits
                    await asyncio.sleep(random.uniform(3, 5))
                    
                    if len(reviews_data) > 0:
                        logger.info(f"📊 Collected {len(reviews_data)} reviews so far...")

            except Exception as e:
                logger.error(f"❌ Scraper Failure: {str(e)}")
            finally:
                await browser.close()
                logger.info(f"✅ Scraping Cycle Finished. Total Captured: {len(reviews_data)}")

        return reviews_data[:limit]

# --- Compatibility Aliases ---
# These ensure your main app (main.py or app.py) can still call the function
scrape_google_reviews = fetch_reviews
run_scraper = fetch_reviews
