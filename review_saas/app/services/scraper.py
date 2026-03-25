import csv
import re
import time
import random
from playwright.sync_api import sync_playwright

# List of proxies from your Smartproxy dashboard
PROXIES = [
    "http://dkgjitgr:uzeqkqwjwmqe@31.59.20.176:6754",
    "http://dkgjitgr:uzeqkqwjwmqe@23.95.150.145:6114",
    "http://dkgjitgr:uzeqkqwjwmqe@198.23.239.134:6540",
    "http://dkgjitgr:uzeqkqwjwmqe@45.38.107.97:6014",
    "http://dkgjitgr:uzeqkqwjwmqe@107.172.163.27:6543"
]

def scrape_google_reviews(search_query, total_reviews_needed=20):
    with sync_playwright() as p:
        # Select a random proxy to avoid detection
        selected_proxy = random.choice(PROXIES)
        
        # Launch browser with proxy configuration
        # Note: set headless=True for Railway deployment
        browser = p.firefox.launch(
            headless=True, 
            proxy={"server": selected_proxy}
        )
        page = browser.new_page()

        # Navigate to Google Maps
        print(f"Searching for: {search_query} using proxy {selected_proxy}")
        page.goto("https://www.google.com/maps", wait_until="networkidle")
        
        # Dismiss cookie consent if it appears
        try:
            page.get_by_role("button", name="Accept all").click()
        except:
            pass

        # Type search query and press Enter
        page.locator("#searchboxinput").fill(search_query)
        page.keyboard.press("Enter")
        
        # Wait for results to load and click the first business
        page.wait_for_selector(".hfpxzc")
        page.locator(".hfpxzc").first.click()

        # Wait for business profile and click the "Reviews" tab
        page.wait_for_selector("button[role='tab'][aria-label*='Reviews']")
        page.get_by_role("button", name=re.compile(r"Reviews", re.IGNORECASE)).click()

        reviews_list = []
        visited_ids = set()

        # Loop until the desired number of reviews is collected
        while len(reviews_list) < total_reviews_needed:
            # Scroll the review panel to trigger loading more reviews
            page.mouse.wheel(0, 3000)
            time.sleep(2) 

            # Locate all visible review containers
            elements = page.locator(".jfti30").all()
            
            for el in elements:
                if len(reviews_list) >= total_reviews_needed:
                    break
                
                # Extract reviewer name
                try:
                    name = el.locator(".d4r55").inner_text()
                except:
                    name = "Unknown"
                
                # Extract star rating using Regex on the aria-label
                try:
                    aria_label = el.locator(".kvS7h").get_attribute("aria-label")
                    rating = re.search(r'\d+', aria_label).group() if aria_label else ""
                except:
                    rating = ""

                # Extract review text and expand "More" button if present
                try:
                    more_btn = el.locator("button:has-text('More')")
                    if more_btn.is_visible():
                        more_btn.click()
                    text = el.locator(".wiI7pd").inner_text()
                except:
                    text = ""

                # Prevent duplicates by checking a unique ID
                review_id = f"{name}-{text[:20]}"
                if review_id not in visited_ids:
                    reviews_list.append({
                        "Name": name, 
                        "Rating": rating, 
                        "Text": text
                    })
                    visited_ids.add(review_id)
            
            print(f"Collected {len(reviews_list)} reviews...")

        browser.close()
        return reviews_list

# CRITICAL: This alias fixes the ImportError in your logs
fetch_reviews = scrape_google_reviews

# For local testing
if __name__ == "__main__":
    data = scrape_google_reviews("Starbucks London", 5)
    print(data)
