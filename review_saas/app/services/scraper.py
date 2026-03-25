import asyncio
import json
import re
import random
import logging
import csv
from datetime import datetime

# =================================================================
# GLOBAL CONFIGURATION & LOGGING
# =================================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("ReviewSaaS.Scraper")

# =================================================================
# RESIDENTIAL PROXY POOL (Smartproxy Dashboard)
# =================================================================
PROXIES = [
    "http://dkgjitgr:uzeqkqwjwmqe@31.59.20.176:6754",
    "http://dkgjitgr:uzeqkqwjwmqe@23.95.150.145:6114",
    "http://dkgjitgr:uzeqkqwjwmqe@198.23.239.134:6540",
    "http://dkgjitgr:uzeqkqwjwmqe@45.38.107.97:6014",
    "http://dkgjitgr:uzeqkqwjwmqe@107.172.163.27:6543"
]

# =================================================================
# SCRAPING ENGINE (PLAYWRIGHT ASYNC)
# =================================================================
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

async def fetch_reviews(place_id: str, limit: int = 50):
    """
    Core function to scrape Google Reviews.
    Aligned 100% with video logic and class selectors.
    """
    logger.info(f"🚀 Initializing Master Scraper for: {place_id}")
    
    reviews_data = []
    visited_ids = set()
    selected_proxy = random.choice(PROXIES)

    async with async_playwright() as p:
        # Launching Firefox as per video tutorial requirements
        browser = await p.firefox.launch(
            headless=True,
            proxy={"server": selected_proxy}
        )
        
        # Setting up the browser context with realistic User-Agent
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0"
        )
        
        page = await context.new_page()
        await stealth_async(page)

        # ---------------------------------------------------------
        # DATA INTERCEPTION LOGIC (BatchExecute)
        # ---------------------------------------------------------
        async def handle_response(response):
            if "batchexecute" in response.url:
                try:
                    text = await response.text()
                    # Google JSON cleanup
                    cleaned_text = text.replace(")]}'", "").strip()
                    
                    # Search for review data patterns in the network stream
                    matches = re.findall(r'\["wrb\.fr".*?\]\]', cleaned_text)
                    
                    for match in matches:
                        outer_json = json.loads(match)
                        inner_json = json.loads(outer_json[2])
                        
                        for data_block in inner_json:
                            if isinstance(data_block, list):
                                for review_item in data_block:
                                    try:
                                        # Mapping Google's internal array indices
                                        rev_id = review_item[0]
                                        if rev_id not in visited_ids:
                                            reviews_data.append({
                                                "review_id": rev_id,
                                                "author": review_item[1][0],
                                                "rating": review_item[4],
                                                "text": review_item[3],
                                                "date": review_item[27] if len(review_item) > 27 else "N/A",
                                                "scraped_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                            })
                                            visited_ids.add(rev_id)
                                    except (IndexError, TypeError):
                                        continue
                except Exception:
                    pass

        # Register the network listener
        page.on("response", handle_response)

        # ---------------------------------------------------------
        # NAVIGATION & INTERACTION
        # ---------------------------------------------------------
        url = f"https://www.google.com/maps/place/?q=place_id0{place_id}&hl=en"
        
        try:
            # Navigate to the target page
            await page.goto(url, wait_until="networkidle", timeout=60000)
            
            # Implementation of the Infinite Scroll Loop
            logger.info("Starting scroll sequence to load data...")
            scroll_attempts = 0
            max_attempts = (limit // 10) + 5

            while len(reviews_data) < limit and scroll_attempts < max_attempts:
                # Scroll the review panel
                await page.mouse.wheel(0, 4000)
                
                # Humanized delay to prevent IP flagging
                await asyncio.sleep(random.uniform(3.0, 5.5))
                
                scroll_attempts += 1
                logger.info(f"Current count: {len(reviews_data)} / {limit}")

        except Exception as e:
            logger.error(f"❌ Scraper critical failure: {str(e)}")
        
        finally:
            # Clean up browser resources
            await browser.close()

    return reviews_data[:limit]

# =================================================================
# COMPATIBILITY ALIAS & EXPORT
# =================================================================
scrape_google_reviews = fetch_reviews

def save_results_to_csv(data, filename="scraped_reviews.csv"):
    """Saves the extracted dictionary list to a local CSV file."""
    if not data:
        print("No data found to save.")
        return
        
    keys = data[0].keys()
    with open(filename, 'w', newline='', encoding='utf-8') as output_file:
        dict_writer = csv.DictWriter(output_file, fieldnames=keys)
        dict_writer.writeheader()
        dict_writer.writerows(data)
    print(f"📁 Data exported successfully to {filename}")

# =================================================================
# TEST EXECUTION
# =================================================================
if __name__ == "__main__":
    # Test using a known Place ID
    SAMPLE_PLACE_ID = "ChIJN1t_tDeuEmsRUoG3yEAt848"
    
    # Run the asynchronous loop
    final_output = asyncio.run(fetch_reviews(SAMPLE_PLACE_ID, limit=20))
    save_results_to_csv(final_output)
