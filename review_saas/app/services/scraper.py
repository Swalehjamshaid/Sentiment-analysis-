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

# YOUR SCRAPEOPS API KEY (From your dashboard screenshot)
SCRAPEOPS_API_KEY = "d6879aef-d2a6-4422-9b6d-14ff099a538f" 

# ScrapeOps Proxy Integration Settings
# We use the 'scrapeops' username and API key as the password
PROXY_SETTINGS = {
    "server": "http://residential-proxy.scrapeops.io:8181",
    "username": "scrapeops",
    "password": SCRAPEOPS_API_KEY
}

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
]

# =================================================================
# CORE SCRAPER FUNCTION
# =================================================================
async def fetch_reviews(place_id: str, limit: int = 50):
    """
    Complete Playwright Scraper using ScrapeOps Residential Aggregator.
    Optimized for Google Maps BatchExecute review interception.
    """
    logger.info(f"🚀 Initializing Master Scraper for Place ID: {place_id}")
    
    reviews_data = []
    visited_ids = set()

    async with async_playwright() as p:
        # Launch Chromium using the ScrapeOps Tunnel
        try:
            browser = await p.chromium.launch(
                headless=True,
                proxy=PROXY_SETTINGS,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu"
                ]
            )
        except Exception as e:
            logger.error(f"❌ Failed to launch browser via Proxy Tunnel: {e}")
            return []

        # Create a fresh context with a random User Agent
        context = await browser.new_context(
            user_agent=random.choice(USER_AGENTS),
            viewport={'width': 1280, 'height': 800}
        )

        page = await context.new_page()
        
        # Apply stealth to mask automation fingerprints
        await stealth_async(page)

        # --- BANDWIDTH SAVER ---
        # Crucial for Residential Proxies: Abort media requests to save your trial data
        await page.route("**/*.{png,jpg,jpeg,gif,webp,svg,mp4,woff2,otf,ttf}", lambda route: route.abort())

        # --- DATA INTERCEPTION LOGIC ---
        async def handle_response(response):
            if "batchexecute" in response.url:
                try:
                    text = await response.text()
                    # Remove Google's anti-XSS prefix
                    cleaned_text = text.replace(")]}'", "").strip()
                    
                    # Search for review data blocks using Regex
                    matches = re.findall(r'\["wrb\.fr".*?\]\]', cleaned_text)
                    for match in matches:
                        # Parse the nested JSON structure
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
                                except (IndexError, TypeError, KeyError):
                                    continue
                except Exception:
                    pass

        # Listen to all network responses
        page.on("response", handle_response)

        # --- NAVIGATION ---
        # We use the standard Google Maps place review endpoint
        target_url = f"https://www.google.com/maps/search/?api=1&query_place_id={place_id}&hl=en"

        try:
            logger.info(f"📡 Navigating Tunnel to: {target_url}")
            
            # Using 'load' with a 90s timeout for slower residential proxy connections
            await page.goto(target_url, wait_until="load", timeout=90000)

            # --- SCROLLING SEQUENCE ---
            scrolls = 0
            max_scrolls = (limit // 5) + 12
            
            while len(reviews_data) < limit and scrolls < max_scrolls:
                # Scroll down in the review pane
                await page.mouse.wheel(0, 3500)
                
                # Human-like delay to allow BatchExecute requests to trigger
                await asyncio.sleep(random.uniform(3.5, 5.5))
                
                scrolls += 1
                if len(reviews_data) > 0:
                    logger.info(f"📊 Current Progress: {len(reviews_data)} / {limit} reviews collected.")

        except Exception as e:
            logger.error(f"❌ Scraper failure during execution: {str(e)}")
        finally:
            # Always ensure the browser closes to prevent memory leaks
            await browser.close()
            logger.info(f"✅ Scraper cycle finished. Total Captured: {len(reviews_data)}")

    return reviews_data[:limit]

# Aliases for application integration
scrape_google_reviews = fetch_reviews
run_scraper = fetch_reviews
