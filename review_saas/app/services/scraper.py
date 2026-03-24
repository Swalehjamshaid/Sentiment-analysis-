import os
import asyncio
import json
import httpx
from typing import Dict, List

# 1. API Configuration
# On Railway, set SCRAPELESS_API_KEY in the 'Variables' tab.
# For local testing, you can replace the getenv with your sk_... string.
SCRAPELESS_API_KEY = os.getenv("SCRAPELESS_API_KEY", "sk_eFUsJD1Cyq4r4BASJhwJxOaasCYcmSeggZRcVN6e5Gk881q0NPgTVTx4GFvflGQc")
SCRAPELESS_ENDPOINT = "https://api.scrapeless.com/api/v1/unlocker/request"

def clean(text: str) -> str:
    """Standardizes spacing and removes newlines."""
    return " ".join(text.split()) if text else ""

def parse_reviews(raw: str) -> List[Dict]:
    """Parses Google Maps internal JSON data."""
    reviews = []
    try:
        # Google's internal JSON often starts with a security prefix
        if raw.startswith(")]}'"):
            raw = raw[4:]
        
        data = json.loads(raw)
        
        # Structure check for Google Maps listentitiesreviews
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
            except (IndexError, TypeError):
                continue
    except Exception as e:
        print(f"❌ Parsing error: {e}")
    return reviews

async def fetch_reviews_via_scrapeless(place_id: str, limit: int = 100):
    """
    Uses the Scrapeless Unlocker (WebUnlocker) to fetch reviews.
    Matches the 'Universal Scraping API' config from your dashboard.
    """
    if not SCRAPELESS_API_KEY:
        raise ValueError("SCRAPELESS_API_KEY is missing!")

    # Target the internal Google Review feed URL
    # The !3i parameter controls the count of reviews returned
    target_url = f"https://www.google.com/maps/preview/review/listentitiesreviews?authuser=0&hl=en&gl=us&pb=!1m2!1y{place_id}!2m2!1i0!3i{limit}!4m5!2b1!3b1!5b1!6b1!7b1"

    headers = {
        "x-api-token": SCRAPELESS_API_KEY,
        "Content-Type": "application/json"
    }

    # Payload matching the 'Unlocker' configuration in your screenshot
    payload = {
        "actor": "unlocker.webunlocker",
        "proxy": {
            "country": "ANY"  # This is the 'World Wide' setting
        },
        "input": {
            "url": target_url,
            "method": "GET"
        }
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        print(f"🚀 [Unlocker] Requesting reviews for Place: {place_id}...")
        
        try:
            response = await client.post(SCRAPELESS_ENDPOINT, headers=headers, json=payload)
            
            if response.status_code != 200:
                print(f"❌ Scrapeless Error: {response.status_code} - {response.text}")
                return []

            result_data = response.json()
            
            # The WebUnlocker returns the raw content of the target URL in 'content'
            raw_content = result_data.get("content", "")
            
            if not raw_content:
                print("⚠️ Scrapeless returned empty content.")
                return []

            return parse_reviews(raw_content)

        except Exception as e:
            print(f"⚠️ Network error during Scrapeless request: {e}")
            return []

async def main():
    # Example Place ID (Replace this with your target)
    PLACE_ID = "ChIJ8S6kk9YJGTkRWK6XHzCKSrA"
    
    # We set a limit of 50 reviews for this test run
    reviews = await fetch_reviews_via_scrapeless(PLACE_ID, limit=50)
    
    if reviews:
        print(f"✅ Successfully captured {len(reviews)} reviews.")
        
        # Save results for your Sentiment Analysis backend
        with open("master_reviews.json", "w", encoding="utf-8") as f:
            json.dump(reviews, f, indent=4, ensure_ascii=False)
            print("💾 Data saved to master_reviews.json")
    else:
        print("❌ Failed to capture reviews.")

if __name__ == "__main__":
    asyncio.run(main())
