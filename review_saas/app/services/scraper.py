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

# Webshare Credentials from Railway Environment Variables
PROXY_SERVER = os.getenv("PROXY_SERVER", "http://p.webshare.io:80")
PROXY_USER = os.getenv("PROXY_USERNAME")
PROXY_PASS = os.getenv("PROXY_PASSWORD")

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
]

# =================================================================
# CORE SCRAPER FUNCTION
# =================================================================
async def fetch_reviews(place_id: str, limit: int = 50):
    """
    Full Playwright Scraper optimized for Railway + Webshare Proxies.
    """
    logger.info(f"🚀 [Railway] Starting Webshare Scraper for: {place_id}")
    
    if not PROXY_USER or not PROXY_PASS:
        logger.error("❌ PROXY_USERNAME or PROXY_PASSWORD missing in Railway Variables!")
        return []

    reviews_data = []
    visited_ids = set()

    async with async_playwright() as p:
        try:
            # Launch Chromium via Webshare Proxy
            browser = await p.chromium.launch(
                headless=True,
                proxy={
                    "server": PROXY_SERVER,
                    "username": PROXY_USER,
                    "password": PROXY_PASS
                },
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                ]
            )
        except Exception as e:
            logger.error(f"❌ Webshare Proxy Launch Failed: {e}")
            return []

        context = await browser.new_context(
            user_agent=random.choice(USER_AGENTS),
            viewport={'width': 1280, 'height': 800}
        )

        page = await context.new_page()
        await stealth_async(page)

        # Optimize for Railway RAM
        await page.route("**/*.{png,jpg,jpeg,gif,webp,svg,mp4,woff2,css}", lambda route: route.abort())

        # Data Interception
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
                                    if r[0] not in visited_ids:
                                        reviews_data.append({
                                            "review_id": r[0],
                                            "author_name": r[1][0],
                                            "rating": r[4],
                                            "text": r[3] if r[3] else "",
                                            "scraped_at": datetime.utcnow().isoformat()
                                        })
                                        visited_ids.add(r[0])
                                except: continue
                except Exception: pass

        page.on("response", handle_response)
        url = f"https://www.google.com/maps/search/?api=1&query=Google&query_place_id={place_id}"

        try:
            logger.info(f"📡 Navigating through Webshare Proxy...")
            await page.goto(url, wait_until="load", timeout=90000)

            # Scroll to trigger data
            for _ in range((limit // 5) + 5):
                if len(reviews_data) >= limit: break
                await page.mouse.wheel(0, 4000)
                await asyncio.sleep(5)
                if len(reviews_data) > 0:
                    logger.info(f"📊 Progress: {len(reviews_data)} reviews found.")

        except Exception as e:
            logger.error(f"❌ Scraper failure: {str(e)}")
        finally:
            await browser.close()
            logger.info(f"✅ Finished. Total: {len(reviews_data)}")

    return reviews_data[:limit]

scrape_google_reviews = fetch_reviews
run_scraper = fetch_reviews
