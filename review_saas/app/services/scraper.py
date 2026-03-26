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
# LOGGING CONFIG
# =========================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("ReviewSaaS.Scraper")

# =========================
# PROXY POOL (Residential)
# =========================
# These are your home residential proxies
PROXIES = [
    "http://dkgjitgr:uzeqkqwjwmqe@31.59.20.176:6754",
    "http://dkgjitgr:uzeqkqwjwmqe@23.95.150.145:6114",
    "http://dkgjitgr:uzeqkqwjwmqe@198.23.239.134:6540",
    "http://dkgjitgr:uzeqkqwjwmqe@45.38.107.97:6014",
    "http://dkgjitgr:uzeqkqwjwmqe@107.172.163.27:6543"
]

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
]

def parse_proxy(proxy_url):
    """Formats the proxy string for Playwright consumption."""
    if "@" in proxy_url:
        creds, server = proxy_url.split("@")
        username, password = creds.replace("http://", "").split(":")
        return {"server": f"http://{server}", "username": username, "password": password}
    return {"server": proxy_url}

# =========================
# MAIN SCRAPER FUNCTION
# =========================
async def fetch_reviews(place_id: str, limit: int = 50):
    """
    Advanced Playwright Scraper using BatchExecute interception.
    Uses home proxies for high-anonymity scraping.
    """
    logger.info(f"🚀 Initializing Master Scraper for: {place_id}")

    reviews_data = []
    visited_ids = set()
    
    # LOGISTICS CHECK: Try Scrapeless first if key is present, otherwise use home PROXIES list
    scrapeless_key = os.getenv("SCRAPELESS_API_KEY")
    if scrapeless_key:
        selected_proxy = {"server": f"http://scraperapi:{scrapeless_key}@proxy-server.scrapeless.com:8001"}
        logger.info("📡 Using Scrapeless Proxy via Environment Variable")
    else:
        # Pick a random proxy from your Residential list
        selected_proxy = parse_proxy(random.choice(PROXIES))
        logger.info(f"📡 Using Residential Home Proxy: {selected_proxy['server']}")

    async with async_playwright() as p:
        # Launch Chromium with Linux-friendly arguments for Railway
        browser = await p.chromium.launch(
            headless=True,
            proxy=selected_proxy,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ]
        )

        context = await browser.new_context(
            user_agent=random.choice(USER_AGENTS),
            viewport={'width': 1920, 'height': 1080}
        )

        page = await context.new_page()
        
        # Apply stealth to hide the scraper from Google
        await stealth_async(page)

        # --- NETWORK DATA INTERCEPTION (BatchExecute) ---
        async def handle_response(response):
            if "batchexecute" in response.url:
                try:
                    text = await response.text()
                    cleaned_text = text.replace(")]}'", "").strip()
                    matches = re.findall(r'\["wrb\.fr".*?\]\]', cleaned_text)
                    for match in matches:
                        try:
                            # Direct JSON extraction from Google's response stream
                            inner_json = json.loads(json.loads(match)[2])
                            for block in inner_json:
                                if isinstance(block, list):
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
                                        except (IndexError, TypeError):
                                            continue
                        except Exception:
                            continue
                except Exception:
                    pass

        page.on("response", handle_response)

        # --- NAVIGATION ---
        if str(place_id).startswith("http"):
            url = f"{place_id}&hl=en"
        else:
            url = f"https://www.google.com/maps/place/?q=place_id:{place_id}&hl=en"

        try:
            # High timeout for slower residential proxies
            await page.goto(url, wait_until="networkidle", timeout=90000)

            logger.info(f"Starting scroll sequence for limit: {limit}")
            scrolls = 0
            max_scrolls = (limit // 5) + 15 

            while len(reviews_data) < limit and scrolls < max_scrolls:
                # Scroll down to trigger more BatchExecute calls
                await page.mouse.wheel(0, 4000)
                await asyncio.sleep(random.uniform(3.0, 5.0))
                scrolls += 1

                if len(reviews_data) > 0:
                    logger.info(f"📊 Progress: {len(reviews_data)} / {limit}")

        except Exception as e:
            logger.error(f"❌ Scraper failure: {str(e)}")

        finally:
            await browser.close()
            logger.info(f"✅ Scraper cycle finished. Total Captured: {len(reviews_data)}")

    return reviews_data[:limit]

# ALIASES FOR COMPATIBILITY WITH YOUR MAIN APP
scrape_google_reviews = fetch_reviews
run_scraper = fetch_reviews
