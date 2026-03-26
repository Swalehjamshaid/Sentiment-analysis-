import asyncio
import json
import re
import random
import logging
import csv
from datetime import datetime
# ALIGNED: Changed back to standard playwright to match your requirements.txt
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
# CORE SCRAPER ENGINE
# =================================================================
async def fetch_reviews(place_id: str, limit: int = 50):
    """
    Advanced Playwright Scraper using BatchExecute interception.
    100% Aligned with Review.py model mapping.
    """
    logger.info(f"🚀 Initializing Master Scraper for: {place_id}")
    
    reviews_data = []
    visited_ids = set()
    selected_proxy = random.choice(PROXIES)

    async with async_playwright() as p:
        # Launching Chromium with required Cloud/Docker flags
        browser = await p.chromium.launch(
            headless=True,
            proxy={"server": selected_proxy},
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
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
                            inner_json = json.loads(json.loads(match)[2])
                            
                            for block in inner_json:
                                if isinstance(block, list):
                                    for r in block:
                                        try:
                                            r_id = r[0]
                                            if r_id not in visited_ids:
                                                # KEY MAPPING SYNCED WITH Review.py:
                                                reviews_data.append({
                                                    "review_id": r_id,           # Used by Review.google_review_id
                                                    "author_name": r[1][0],      # Used by Review.author_name
                                                    "rating": r[4],             # Used by Review.rating
                                                    "text": r[3],               # Used by Review.text
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
        if str(place_id).startswith("http"):
            url = f"{place_id}&hl=en"
        else:
            url = f"https://www.google.com/maps/place/?q=place_id:{place_id}&hl=en"
        
        try:
            await page.goto(url, wait_until="networkidle", timeout=90000)
            
            logger.info(f"Starting scroll sequence for limit: {limit}")
            scrolls = 0
            max_scrolls = (limit // 10) + 15 

            while len(reviews_data) < limit and scrolls < max_scrolls:
                await page.mouse.wheel(0, 4000)
                await asyncio.sleep(random.uniform(3.0, 5.0))
                scrolls += 1
                if len(reviews_data) > 0:
                    logger.info(f"Progress: {len(reviews_data)} / {limit} (Synced)")

        except Exception as e:
            logger.error(f"❌ Scraper failure: {str(e)}")
        
        finally:
            await browser.close()
            logger.info("Browser closed successfully.")

    return reviews_data[:limit]

# ALIAS FOR BACKEND ROUTE COMPATIBILITY
scrape_google_reviews = fetch_reviews

def save_to_csv(data, filename="scraped_reviews.csv"):
    if not data: return
    keys = data[0].keys()
    with open(filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(data)
