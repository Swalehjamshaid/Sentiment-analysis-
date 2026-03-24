import os
import asyncio
import json
import httpx  # Using httpx for async requests
from typing import Dict, List

# Load API Key from Railway Environment Variables
SCRAPELESS_API_KEY = os.getenv("SCRAPELESS_API_KEY")

def clean(text: str) -> str:
    return " ".join(text.split()) if text else ""

def parse_reviews(raw: str) -> List[Dict]:
    reviews = []
    try:
        # Some Google responses start with security prefix
        if raw.startswith(")]}'"):
            raw = raw[4:]
        data = json.loads(raw)
        
        # This parsing logic matches the specific Google Maps review JSON structure
        if len(data) < 3 or not data[2]:
            return []
            
        for r in data[2]:
            try:
                reviews.append({
                    "review_id": r[0],
                    "author": r[1][0] if r[1] else "Anonymous",
                    "rating": r[4],
                    "text": clean(r[3]),
                    "relative_time": r[14],
                    "total_author_reviews": r[12][1][1] if r[12] and r[12][1] else 0
                })
            except:
                continue
    except Exception as e:
        print(f"Parsing error: {e}")
    return reviews

async def fetch_reviews_via_scrapeless(place_id: str, limit: int = 100):
    """
    Uses Scrapeless to fetch Google Maps reviews.
    Scrapeless handles the browser, proxies, and anti-bot.
    """
    if not SCRAPELESS_API_KEY:
        raise ValueError("SCRAPELESS_API_KEY is missing! Add it to Railway Variables.")

    # Scrapeless Scraper API Endpoint
    api_url = "https://api.scrapeless.com/api/v1/scraper/request"
    
    # We target the Mobile Google Maps URL
    target_url = f"https://www.google.com/maps/preview/review/listentitiesreviews?authuser=0&hl=en&gl=us&pb=!1m2!1y{place_id}!2m2!1i0!3i{limit}!4m5!2b1!3b1!5b1!6b1!7b1"

    headers = {
        "x-api-token": SCRAPELESS_API_KEY,
        "Content-Type": "application/json"
    }

    # Payload for Scrapeless
    # We use 'collector' or 'browser' depending on the site. 
    # For Google Maps data feeds, 'browser.chrome' is safest.
    payload = {
        "actor": "browser.chrome",
        "input": {
            "url": target_url,
            "proxy_country": "US",
            "wait_until": "networkidle"
        }
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        print(f"🚀 Requesting data from Scrapeless for Place: {place_id}...")
        
        response = await client.post(api_url, headers=headers, json=payload)
        
        if response.status_code != 200:
            print(f"❌ Scrapeless Error: {response.status_code} - {response.text}")
            return []

        result_data = response.json()
        
        # Scrapeless usually returns the raw response body in the 'content' field
        raw_content = result_data.get("content", "")
        
        if not raw_content:
            print("⚠️ No content returned from Scrapeless.")
            return []

        reviews = parse_reviews(raw_content)
        return reviews[:limit]

async def main():
    # Example Place ID
    PLACE_ID = "ChIJ8S6kk9YJGTkRWK6XHzCKSrA"
    
    try:
        reviews = await fetch_reviews_via_scrapeless(PLACE_ID, limit=50)
        
        print(f"✅ Successfully captured {len(reviews)} reviews.")
        
        # Save to file
        with open("master_reviews.json", "w", encoding="utf-8") as f:
            json.dump(reviews, f, indent=4, ensure_ascii=False)
            
    except Exception as e:
        print(f"⚠️ Process Failed: {e}")

if __name__ == "__main__":
    asyncio.run(main())
