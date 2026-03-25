import asyncio
import json
import re
import random
import logging
import csv
from datetime import datetime
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

# =================================================================
# LOGGING & CONFIGURATION
# =================================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("ReviewSaaS.Scraper")

# SMARTPROXY RESIDENTIAL POOL
PROXIES = [
    "http://dkgjitgr:uzeqkqwjwmqe@31.59.20.176:6754",
    "http://dkgjitgr:uzeqkqwjwmqe@23.95.150.145:6114",
    "http://dkgjitgr:uzeqkqwjwmqe@198.23.239.134:6540",
    "http://dkgjitgr:uzeqkqwjwmqe@45.38.107.97:6014",
    "http://dkgjitgr:uzeqkqwjwmqe@107.172.163.27:6543"
]

# =================================================================
# CORE SCRAPER ENGINE (SYNCED WITH BACKEND)
# =================================================================
async def fetch_reviews(place_id: str, limit: int = 50):
    """
    Advanced Playwright Scraper using BatchExecute interception.
    Updated with Cloud-compatible flags for Railway deployment.
    """
    logger.info(f"🚀 Initializing Master Scraper for: {place_id}")
    
    reviews_data = []
    visited_ids = set()
    selected_proxy = random.choice(PROXIES)

    async with async_playwright() as p:
        # =================================================================
        # CRITICAL FIX FOR RAILWAY/DOCKER:
        # Added --no-sandbox, --disable-dev-shm-usage, and --disable-gpu
        # =================================================================
        browser = await p.chromium.launch(
            headless=True,
            proxy={"server": selected_proxy},
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-software-rasterizer",
                "--single-process"
            ]
        )
        
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        
        page = await context.new_page()
        await stealth_async(page)

        # --- NETWORK DATA INTERCEPTION ---
        async def handle_response(response):
            if "batchexecute" in response.url:
                try:
                    text = await response.text()
                    cleaned_text = text.replace(")]}'", "").strip()
                    
                    # Intercepting the 'wrb.fr' data arrays
                    matches = re.findall(r'\["wrb\.fr".*?\]\]', cleaned_text)
                    
                    for match in matches:
                        try:
                            # Double-decode the nested JSON structure in BatchExecute
                            raw_json = json.loads(match)
                            inner_json = json.loads(raw_json[2])
                            
                            for block in inner_json:
                                if isinstance(block, list):
                                    for r in block:
                                        try:
                                            r_id = r[0]
                                            if r_id not in visited_ids:
                                                reviews_data.append({
                                                    "review_id": r_id,
                                                    "author": r[1][0],
                                                    "rating": r[4],
                                                    "text": r[3],
                                                    "date_text": r[27] if len(r) > 27 else "N/A",
                                                    "scraped_at": datetime.now().isoformat()
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
        # Note: Added hl=en to ensure consistent date parsing
        url = f"https://www.google.com/maps/place/?q=place_id:{place_id}&hl=en"
        
        try:
            # Increased timeout for proxy latency
            await page.goto(url, wait_until="networkidle", timeout=90000)
            
            logger.info("Starting infinite scroll sequence...")
            scrolls = 0
            # Heuristic to ensure we hit the limit
            max_scrolls = (limit // 10) + 15 

            # Target the specific scrollable container for reviews if possible
            # or use the generic wheel scroll
            while len(reviews_data) < limit and scrolls < max_scrolls:
                await page.mouse.wheel(0, 4000)
                # Random sleep helps bypass bot detection
                await asyncio.sleep(random.uniform(2.5, 4.5))
                scrolls += 1
                logger.info(f"Progress: {len(reviews_data)} / {limit} fetched.")

        except Exception as e:
            logger.error(f"❌ Scraper failure: {str(e)}")
        
        finally:
            await browser.close()
            logger.info("Browser closed.")

    return reviews_data[:limit]

# ALIAS FOR BACKEND ROUTE COMPATIBILITY
scrape_google_reviews = fetch_reviews

# =================================================================
# DATA EXPORT & LOCAL TESTING
# =================================================================
def save_to_csv(data, filename="scraped_reviews.csv"):
    if not data: 
        logger.warning("No data to save.")
        return
    keys = data[0].keys()
    with open(filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(data)

if __name__ == "__main__":
    # Test with a known Place ID
    TEST_ID = "ChIJDVYKpFEEGTkRp_XASXZ21Tc" 
    results = asyncio.run(fetch_reviews(TEST_ID, limit=20))
    save_to_csv(results)
