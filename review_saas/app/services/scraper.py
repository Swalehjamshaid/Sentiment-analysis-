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
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("ReviewSaaS.Scraper")

# Fetches your verified key from Railway Variables
# d6879aef-d2a6-4422-9b6d-14ff099a538f
SCRAPEOPS_API_KEY = os.getenv("SCRAPEOPS_API_KEY")

# PROXY CONFIGURATION: Directly from your ScrapeOps dashboard screenshots
# Host: residential-proxy.scrapeops.io
# Port: 8181
PROXY_SETTINGS = {
    "server": "http://residential-proxy.scrapeops.io:8181",
    "username": "scrapeops",
    "password": SCRAPEOPS_API_KEY
}

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
]

# =================================================================
# CORE SCRAPER FUNCTION
# =================================================================
async def fetch_reviews(place_id: str, limit: int = 50):
    """
    Railway-optimized Playwright scraper using ScrapeOps Residential Proxy Aggregator.
    """
    logger.info(f"🚀 [Railway] Starting Master Scraper for: {place_id}")
    
    if not SCRAPEOPS_API_KEY:
        logger.error("❌ SCRAPEOPS_API_KEY not found in environment variables!")
        return []

    reviews_data = []
    visited_ids = set()

    async with async_playwright() as p:
        try:
            # Launching via the ScrapeOps Tunnel on Port 8181
            browser = await p.chromium.launch(
                headless=True,
                proxy=PROXY_SETTINGS,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--ignore-certificate-errors" # Aligned with ScrapeOps SSL note
                ]
            )
        except Exception as e:
            logger.error(f"❌ Proxy Tunnel Failed: {e}")
            return []

        context = await browser.new_context(
            user_agent=random.choice(USER_AGENTS),
            viewport={'width': 1280, 'height': 800}
        )

        page = await context.new_page()
        await stealth_async(page)

        # BANDWIDTH SAVER: Abort images/media to preserve your 500MB free trial
        await page.route("**/*.{png,jpg,jpeg,gif,webp,svg,mp4,woff2,css}", lambda route: route.abort())

        # DATA INTERCEPTION: Capturing Google's BatchExecute stream
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
                                            "date": r[27] if len(r) > 27 else "N/A",
                                            "scraped_at": datetime.utcnow().isoformat()
                                        })
                                        visited_ids.add(r_id)
                                except: continue
                except: pass

        page.on("response", handle_response)

        # Target Google Maps review URL
        url = f"https://www.google.com/maps/search/?api=1&query=Google&query_place_id={place_id}"

        try:
            logger.info(f"📡 Navigating through ScrapeOps Gateway...")
            # Increased timeout to 120s for residential proxy latency
            await page.goto(url, wait_until="load", timeout=120000)

            # Scrolling logic to trigger data batches
            for _ in range((limit // 5) + 10):
                if len(reviews_data) >= limit: break
                await page.mouse.wheel(0, 4000)
                await asyncio.sleep(random.uniform(4.0, 6.0))
                if len(reviews_data) > 0:
                    logger.info(f"📊 Collected {len(reviews_data)} reviews so far...")

        except Exception as e:
            logger.error(f"❌ Railway Execution Error: {str(e)}")
        finally:
            await browser.close()
            logger.info(f"✅ Scraping Complete. Captured: {len(reviews_data)}")

    return reviews_data[:limit]

# Aliases
scrape_google_reviews = fetch_reviews
run_scraper = fetch_reviews
