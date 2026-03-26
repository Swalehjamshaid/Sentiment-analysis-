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

# YOUR CONFIRMED API KEY
SCRAPEOPS_API_KEY = "d6879aef-d2a6-4422-9b6d-14ff099a538f" 

# ScrapeOps Proxy Integration
# Server: residential-proxy.scrapeops.io:8181
# User: scrapeops
# Password: [Your API Key]
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
    """
    logger.info(f"🚀 Initializing Master Scraper for: {place_id}")
    reviews_data = []
    visited_ids = set()

    async with async_playwright() as p:
        # Launch Chromium via ScrapeOps Tunnel
        try:
            browser = await p.chromium.launch(
                headless=True,
                proxy=PROXY_SETTINGS,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                ]
            )
        except Exception as e:
            logger.error(f"❌ Failed to launch browser via Proxy: {e}")
            return []

        context = await browser.new_context(
            user_agent=random.choice(USER_AGENTS),
            viewport={'width': 1280, 'height': 800}
        )

        page = await context.new_page()
        await stealth_async(page)

        # --- BANDWIDTH SAVER ---
        # Blocks images to save your free trial data
        await page.route("**/*.{png,jpg,jpeg,gif,webp,svg,mp4,woff2}", lambda route: route.abort())

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

        # --- NAVIGATION ---
        # Fixed URL format for Google Maps reviews
        url = f"https://www.google.com/maps/search/?api=1&query_place_id={place_id}&hl=en"

        try:
            logger.info(f"📡 Navigating through ScrapeOps Tunnel to: {url}")
            # Use 'load' to ensure the proxy tunnel is established
            await page.goto(url, wait_until="load", timeout=90000)

            # Scroll loop to trigger more reviews
            scrolls = 0
            max_scrolls = (limit // 5) + 10
            
            while len(reviews_data) < limit and scrolls < max_scrolls:
                await page.mouse.wheel(0, 3500)
                await asyncio.sleep(random.uniform(3.0, 5.0))
                scrolls += 1
                if len(reviews_data) > 0:
                    logger.info(f"📊 Collected {len(reviews_data)} reviews so far...")

        except Exception as e:
            logger.error(f"❌ Scraper failure: {str(e)}")
        finally:
            await browser.close()
            logger.info(f"✅ Finished. Total Captured: {len(reviews_data)}")

    return reviews_data[:limit]

# Aliases for compatibility
scrape_google_reviews = fetch_reviews
run_scraper = fetch_reviews
