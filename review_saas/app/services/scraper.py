import asyncio
import json
import re
import random
import logging
import csv

# Professional Scraping Engines
from patchright.async_api import async_playwright as patchright_playwright
from playwright.async_api import async_playwright as playwright
from playwright_stealth import stealth_async
import requests

# Logger configuration for real-time tracking
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ReviewSaaS.Master")

# ==========================================
# 1. UPDATED PROXY POOL (From your Dashboard)
# ==========================================
PROXIES = [
    "http://dkgjitgr:uzeqkqwjwmqe@31.59.20.176:6754",
    "http://dkgjitgr:uzeqkqwjwmqe@23.95.150.145:6114",
    "http://dkgjitgr:uzeqkqwjwmqe@198.23.239.134:6540",
    "http://dkgjitgr:uzeqkqwjwmqe@45.38.107.97:6014",
    "http://dkgjitgr:uzeqkqwjwmqe@107.172.163.27:6543"
]

# ==========================================
# 2. ENGINE 1: PATCHRIGHT (Video-Aligned Logic)
# ==========================================
async def engine_patchright(place_id, limit):
    """
    Primary Engine: Uses the 'batchexecute' interception 
    method shown in the advanced portion of the tutorial.
    """
    logger.info("🚀 Engine 1: Patchright Starting (Stealth Mode)")
    proxy = random.choice(PROXIES)

    async with patchright_playwright() as p:
        browser = await p.chromium.launch(
            headless=True, # Set to False if you want to see the browser
            proxy={"server": proxy}
        )

        context = await browser.new_context()
        page = await context.new_page()
        await stealth_async(page) # Hides automation signatures

        reviews = []

        # Listener to catch the raw JSON data Google sends to the browser
        async def handle_response(response):
            if "batchexecute" in response.url:
                try:
                    text = await response.text()
                    clean = text.replace(")]}'", "")
                    matches = re.findall(r'\["wrb\.fr".*?\]\]', clean)

                    for m in matches:
                        raw = json.loads(m)
                        inner = json.loads(raw[2])
                        for block in inner:
                            for r in block:
                                try:
                                    reviews.append({
                                        "author": r[1][0],
                                        "rating": r[4],
                                        "text": r[3],
                                        "id": r[0]
                                    })
                                except: continue
                except: pass

        page.on("response", handle_response)

        # Build URL using Place ID
        url = f"https://www.google.com/maps/place/Do+or+Dive+Bar/@40.6867831,-73.9570104,17z/data=!3m23{place_id}&hl=en"
        await page.goto(url, wait_until="networkidle", timeout=60000)

        # Human-like scrolling loop to trigger data loading
        for _ in range(10):
            await page.mouse.wheel(0, 3000)
            await asyncio.sleep(random.uniform(3, 6))

        await browser.close()
        logger.info(f"✅ Patchright recovered {len(reviews)} reviews")
        return reviews[:limit]

# ==========================================
# 3. MASTER CONTROLLER & SAVING
# ==========================================
async def run_scraper(place_id, limit=50):
    # Try the best engine first
    results = await engine_patchright(place_id, limit)
    
    if results:
        # Save results to CSV (Final step of the video)
        keys = results[0].keys()
        with open('google_reviews_master.csv', 'w', newline='', encoding='utf-8') as f:
            dict_writer = csv.DictWriter(f, fieldnames=keys)
            dict_writer.writeheader()
            dict_writer.writerows(results)
        logger.info("📁 Data saved to google_reviews_master.csv")
    else:
        logger.error("❌ No reviews found.")

if __name__ == "__main__":
    # Your target Place ID (Replace with yours)
    TARGET_PLACE_ID = "ChIJN1t_tDeuEmsRUoG3yEAt848"
    asyncio.run(run_scraper(TARGET_PLACE_ID, 30))
