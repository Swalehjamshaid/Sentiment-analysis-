import asyncio
import json
import re
import random
import logging
import csv
from datetime import datetime

# --- CORE LIBRARIES ---
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

# --- LOGGING SETUP ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("ReviewSaaS.Scraper")

# --- SMARTPROXY RESIDENTIAL POOL ---
PROXIES = [
    "http://dkgjitgr:uzeqkqwjwmqe@31.59.20.176:6754",
    "http://dkgjitgr:uzeqkqwjwmqe@23.95.150.145:6114",
    "http://dkgjitgr:uzeqkqwjwmqe@198.23.239.134:6540",
    "http://dkgjitgr:uzeqkqwjwmqe@45.38.107.97:6014",
    "http://dkgjitgr:uzeqkqwjwmqe@107.172.163.27:6543"
]

# =================================================================
# MAIN SCRAPER LOGIC
# =================================================================
async def fetch_reviews(place_id: str, limit: int = 50):
    """
    Advanced Playwright Scraper.
    Uses Network Interception to capture 'batchexecute' JSON data.
    """
    logger.info(f"🚀 Starting Advanced Scrape for Place ID: {place_id}")
    
    reviews_data = []
    visited_ids = set()
    selected_proxy = random.choice(PROXIES)

    async with async_playwright() as p:
        # Launching Chromium (matches your recent Nixpacks config)
        browser = await p.chromium.launch(
            headless=True,
            proxy={"server": selected_proxy}
        )
        
        # Mimic high-end user profile
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        
        page = await context.new_page()
        await stealth_async(page)

        # ---------------------------------------------------------
        # NETWORK INTERCEPTION (The 'Master' Logic)
        # ---------------------------------------------------------
        async def handle_response(response):
            # This intercepts the background data Google sends while scrolling
            if "batchexecute" in response.url:
                try:
                    raw_text = await response.text()
                    # Clean the anti-XSS prefix Google adds
                    cleaned_text = raw_text.replace(")]}'", "").strip()
                    
                    # Regex to find the specific 'wrb.fr' data arrays from the video
                    matches = re.findall(r'\["wrb\.fr".*?\]\]', cleaned_text)
                    
                    for match in matches:
                        outer_json = json.loads(match)
                        inner_json = json.loads(outer_json[2])
                        
                        for block in inner_json:
                            if isinstance(block, list):
                                for item in block:
                                    try:
                                        # Array indices mapped from Google's internal JSON structure
                                        r_id = item[0]
                                        if r_id not in visited_ids:
                                            reviews_data.append({
                                                "review_id": r_id,
                                                "author": item[1][0],
                                                "rating": item[4],
                                                "text": item[3],
                                                "date_text": item[27] if len(item) > 27 else "Unknown",
                                                "scraped_at": datetime.now().isoformat()
                                            })
                                            visited_ids.add(r_id)
                                    except (IndexError, TypeError):
                                        continue
                except Exception:
                    pass

        # Attach the listener
        page.on("response", handle_response)

        # ---------------------------------------------------------
        # NAVIGATION
        # ---------------------------------------------------------
        # Construct direct Google Reviews URL using Place ID
        url = f"https://www.google.com/maps/search/?api=1&query=Google&query_place_id={place_id}"
        
        try:
            await page.goto(url, wait_until="networkidle", timeout=60000)
            
            # Navigate to the Reviews tab if not already there
            try:
                await page.wait_for_selector("button[role='tab'][aria-label*='Reviews']", timeout=5000)
                await page.get_by_role("button", name=re.compile(r"Reviews", re.IGNORECASE)).click()
            except:
                logger.info("Already on reviews page or tab not found.")

            # --- SMART SCROLLING LOOP ---
            logger.info("Executing infinite scroll sequence...")
            scrolls = 0
            max_scrolls = (limit // 10) + 10 # Buffer for deduplication

            while len(reviews_data) < limit and scrolls < max_scrolls:
                # Scroll the central review container
                await page.mouse.wheel(0, 4000)
                
                # Jitter delay: Essential to prevent bot detection
                await asyncio.sleep(random.uniform(2.5, 5.0))
                
                scrolls += 1
                logger.info(f"Capture Progress: {len(reviews_data)} / {limit}")

        except Exception as e:
            logger.error(f"❌ Scraper critical failure: {str(e)}")
        
        finally:
            await browser.close()

    return reviews_data[:limit]

# --- COMPATIBILITY & EXPORT ---
scrape_google_reviews = fetch_reviews

def save_to_csv(data, filename="google_reviews.csv"):
    if not data:
        logger.warning("No data found to save.")
        return
    
    with open(filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=data[0].keys())
        writer.writeheader()
        writer.writerows(data)
    logger.info(f"📁 Successfully exported to {filename}")

# --- LOCAL TEST BLOCK ---
if __name__ == "__main__":
    # Example ID from your logs (Salt'n Pepper Village)
    TARGET_ID = "ChIJDVYKpFEEGTkRp_XASXZ21Tc"
    
    # Run the async loop
    final_results = asyncio.run(fetch_reviews(TARGET_ID, limit=30))
    save_to_csv(final_results)
