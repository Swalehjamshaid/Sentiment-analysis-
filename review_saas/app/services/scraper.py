import asyncio
import json
import re
import random
import logging
import os
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

# Pulling the key from Railway Environment Variables
SCRAPEOPS_API_KEY = os.getenv("SCRAPEOPS_API_KEY")

if not SCRAPEOPS_API_KEY:
    logger.error("❌ SCRAPEOPS_API_KEY not found in Railway environment variables!")

# Proxy Configuration aligned with ScrapeOps Port 8181
# This acts as the gateway to 20+ residential proxy providers
PROXY_SETTINGS = {
    "server": "http://residential-proxy.scrapeops.io:8181",
    "username": "scrapeops",
    "password": SCRAPEOPS_API_KEY
}

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
]

# =================================================================
# CORE SCRAPER FUNCTION
# =================================================================
async def fetch_reviews(place_id: str, limit: int = 50):
    """
    Railway-optimized Playwright scraper using ScrapeOps Residential Proxy.
    Intercepts Google's BatchExecute JSON stream.
    """
    logger.info(f"🚀 [Railway] Initializing Master Scraper for: {place_id}")
    reviews_data = []
    visited_ids = set()

    async with async_playwright() as p:
        try:
            # Launch Chromium through the ScrapeOps Tunnel
            browser = await p.chromium.launch(
                headless=True,
                proxy=PROXY_SETTINGS,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--single-process" 
                ]
            )
        except Exception as e:
            logger.error(f"❌ Railway Tunnel Connection Failed: {e}")
            logger.error("FIX: Ensure 'Whitelisted IPs' is EMPTY in ScrapeOps dashboard.")
            return []

        context = await browser.new_context(
            user_agent=random.choice(USER_AGENTS),
            viewport={'width': 1280, 'height': 800}
        )

        page = await context.new_page()
        await stealth_async(page)

        # --- RESOURCE OPTIMIZATION ---
        # Aborts images/media to stay under Railway's RAM limits and save Proxy bandwidth
        await page.route("**/*.{png,jpg,jpeg,gif,webp,svg,mp4,woff2,css}", lambda route: route.abort())

        # --- DATA INTERCEPTION (BatchExecute) ---
        async def handle_response(response):
            if "batchexecute" in response.url:
                try:
                    text = await response.text()
                    cleaned_text = text.replace(")]}'", "").strip()
                    matches = re.findall(r'\["wrb\.fr".*?\]\]', cleaned_text)
                    for match in matches:
                        inner_json = json.loads(json.loads(match)[2])
                        for block in [b for b in inner_json if isinstance(b, list)]:
                            for r in block:
                                try:
                                    r_id = r[0]
                                    if r_id not in visited_ids:
                                        reviews_data.append({
                                            "review_id": r_id,
                                            "author_name": r[1][0],
                                            "rating": r[4],
                                            "text": r[3] if r[3] else "",
                                            "date_text": r[27] if len(r) > 27 else "N/A",
                                            "scraped_at": datetime.utcnow().isoformat()
                                        })
                                        visited_ids.add(r_id)
                                except (IndexError, TypeError): continue
                except Exception: pass

        page.on("response", handle_response)

        # Standard Google Maps review endpoint
        url = f"https://www.google.com/maps/search/?api=1&query=Google&query_place_id={place_id}"

        try:
            logger.info(f"📡 Navigating Tunnel to: {url}")
            # Extended timeout for slower residential proxy nodes
            await page.goto(url, wait_until="load", timeout=120000)

            scrolls = 0
            max_scrolls = (limit // 5) + 15
            
            while len(reviews_data) < limit and scrolls < max_scrolls:
                await page.mouse.wheel(0, 4000)
                await asyncio.sleep(random.uniform(4.0, 6.0))
                scrolls += 1
                if len(reviews_data) > 0:
                    logger.info(f"📊 Collected {len(reviews_data)} / {limit} reviews...")

        except Exception as e:
            logger.error(f"❌ Railway Execution Failure: {str(e)}")
        finally:
            await browser.close()
            logger.info(f"✅ Finished. Total Captured: {len(reviews_data)}")

    return reviews_data[:limit]

# Aliases for compatibility with your main app
scrape_google_reviews = fetch_reviews
run_scraper = fetch_reviews
