import asyncio
import json
import re
import random
import logging
import os
from datetime import datetime
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

# =========================
# CONFIGURATION & LOGGING
# =========================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("ReviewSaaS.Scraper")

# PASTE YOUR SCRAPEOPS API KEY HERE
SCRAPEOPS_API_KEY = "YOUR_API_KEY_HERE" 

# ScrapeOps Proxy Integration (Matches your screenshot)
PROXY_SETTINGS = {
    "server": "http://residential-proxy.scrapeops.io:8181",
    "username": "scrapeops",
    "password": SCRAPEOPS_API_KEY
}

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
]

# =========================
# CORE SCRAPER FUNCTION
# =========================
async def fetch_reviews(place_id: str, limit: int = 50):
    """
    Playwright Scraper using ScrapeOps Residential Aggregator.
    Optimized for Google's BatchExecute protocol.
    """
    logger.info(f"🚀 Initializing Master Scraper for: {place_id}")
    reviews_data = []
    visited_ids = set()

    async with async_playwright() as p:
        # Launch Chromium via ScrapeOps Proxy
        browser = await p.chromium.launch(
            headless=True,
            proxy=PROXY_SETTINGS,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
            ]
        )

        context = await browser.new_context(
            user_agent=random.choice(USER_AGENTS),
            viewport={'width': 1280, 'height': 800}
        )

        page = await context.new_page()
        await stealth_async(page)

        # --- DATA SAVING OPTIMIZATION ---
        # Blocks images/media to save your ScrapeOps trial bandwidth
        await page.route("**/*.{png,jpg,jpeg,gif,webp,svg,mp4,woff2}", lambda route: route.abort())

        # --- NETWORK INTERCEPTION ---
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

        # --- NAVIGATION ---
        # Constructing a direct Google Maps reviews URL
        url = f"https://www.google.com/maps/search/?api=1&query_place_id={place_id}&hl=en"

        try:
            logger.info(f"📡 Navigating through ScrapeOps to: {url}")
            # Higher timeout for residential latency
            await page.goto(url, wait_until="domcontentloaded", timeout=90000)

            # Scroll loop to trigger BatchExecute calls
            scrolls = 0
            max_scrolls = (limit // 5) + 10
            
            while len(reviews_data) < limit and scrolls < max_scrolls:
                await page.mouse.wheel(0, 3000)
                await asyncio.sleep(random.uniform(2.5, 4.5))
                scrolls += 1
                if len(reviews_data) > 0:
                    logger.info(f"📊 Progress: {len(reviews_data)} / {limit}")

        except Exception as e:
            logger.error(f"❌ Scraper failure: {str(e)}")
        finally:
            await browser.close()
            logger.info(f"✅ Finished. Total Captured: {len(reviews_data)}")

    return reviews_data[:limit]

# Aliases for your app logic
scrape_google_reviews = fetch_reviews
run_scraper = fetch_reviews
