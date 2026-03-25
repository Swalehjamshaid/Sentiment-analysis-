import csv
import re
import time
import random
from playwright.sync_api import sync_playwright

# Proxy pool from your Smartproxy dashboard
PROXIES = [
    "http://dkgjitgr:uzeqkqwjwmqe@31.59.20.176:6754",
    "http://dkgjitgr:uzeqkqwjwmqe@23.95.150.145:6114",
    "http://dkgjitgr:uzeqkqwjwmqe@198.23.239.134:6540",
    "http://dkgjitgr:uzeqkqwjwmqe@45.38.107.97:6014",
    "http://dkgjitgr:uzeqkqwjwmqe@107.172.163.27:6543"
]

# ALIGNED LOGIC: Accept 'place_id' and 'limit' to fix the TypeError
def fetch_reviews(place_id: str, limit: int = 20):
    """
    Scraper logic aligned 100% with the video tutorial.
    Fixed to accept arguments from the FastAPI route.
    """
    with sync_playwright() as p:
        # Select a random proxy from your pool
        selected_proxy = random.choice(PROXIES)
        
        # Launch browser (Headless=True is required for Railway)
        browser = p.firefox.launch(
            headless=True, 
            proxy={"server": selected_proxy}
        )
        page = browser.new_page()

        # 1. Navigate to Google Maps
        print(f"🚀 Starting scrape for: {place_id}")
        page.goto("https://www.google.com/maps", wait_until="networkidle")
        
        # 2. Dismiss cookie consent if it appears
        try:
            page.get_by_role("button", name="Accept all").click()
        except:
            pass

        # 3. Search using the place_id (or business name)
        page.locator("#searchboxinput").fill(place_id)
        page.keyboard.press("Enter")
        
        # 4. Wait for results and click the first business
        page.wait_for_selector(".hfpxzc")
        page.locator(".hfpxzc").first.click()

        # 5. Navigate to the Reviews tab
        page.wait_for_selector("button[role='tab'][aria-label*='Reviews']")
        page.get_by_role("button", name=re.compile(r"Reviews", re.IGNORECASE)).click()

        reviews_list = []
        visited_ids = set()

        # 6. Scrolling Loop (Video Logic)
        while len(reviews_list) < limit:
            # Scroll the review panel
            page.mouse.wheel(0, 3000)
            time.sleep(2) 

            # Locate review containers (Class .jfti30 from video)
            elements = page.locator(".jfti30").all()
            
            for el in elements:
                if len(reviews_list) >= limit:
                    break
                
                # Extract Data
                try:
                    name = el.locator(".d4r55").inner_text()
                    
                    # Rating extraction using Regex
                    aria_label = el.locator(".kvS7h").get_attribute("aria-label")
                    rating = int(re.search(r'\d+', aria_label).group()) if aria_label else 0

                    # Handle "More" button to expand long reviews
                    try:
                        more_btn = el.locator("button:has-text('More')")
                        if more_btn.is_visible():
                            more_btn.click()
                    except:
                        pass
                        
                    text = el.locator(".wiI7pd").inner_text()

                    # Deduplication logic
                    review_id = f"{name}-{text[:20]}"
                    if review_id not in visited_ids:
                        reviews_list.append({
                            "author": name, 
                            "rating": rating, 
                            "text": text
                        })
                        visited_ids.add(review_id)
                except Exception as e:
                    continue
            
            print(f"📊 Progress: {len(reviews_list)}/{limit} reviews collected.")

        browser.close()
        return reviews_list

# This alias ensures the code works even if other parts of the app use the old name
scrape_google_reviews = fetch_reviews
