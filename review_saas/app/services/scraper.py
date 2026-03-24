import os
import json
import asyncio
import httpx
from typing import Dict, List

# 1. API Configuration
# Railway will pull this from your Variables tab. 
# Fallback included for local testing.
SCRAPELESS_API_KEY = os.getenv("SCRAPELESS_API_KEY", "sk_eFUsJD1Cyq4r4BASJhwJxOaasCYcmSeggZRcVN6e5Gk881q0NPgTVTx4GFvflGQc")
SCRAPELESS_ENDPOINT = "https://api.scrapeless.com/api/v1/unlocker/request"

def clean(text: str) -> str:
    """Standardizes spacing and removes newlines for ReviewSaaS processing."""
    return " ".join(text.split()) if text else ""

def parse_reviews_json(raw_data: str) -> List[Dict]:
    """
    Parses Google's 'listentitiesreviews' internal JSON.
    Google prefixes this data with a security string: )]}'\n
    """
    reviews = []
    try:
        # Strip the security prefix if it exists
        if raw_data.startswith(")]}'"):
            raw_data = raw_data[4:]
        
        data = json.loads(raw_data)
        
        # Google Maps JSON structure: Reviews are in the 3rd index (data[2])
        if len(data) > 2 and data[2]:
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
        print(f"❌ Scrapeless Parsing Error: {e}")
    return reviews

async def fetch_reviews(place_id: str, limit: int = 100):
    """
    Main entry point aligned with app/routes/reviews.py.
    Uses Scrapeless Unlocker to fetch data directly from the Google internal API.
    """
    if not SCRAPELESS_API_KEY:
        print("CRITICAL: SCRAPELESS_API_KEY is missing!")
        return []

    # Target URL: Google internal API for reviews
    # !3i{limit} handles the 'scrolling' logic automatically in one request
    target_url = f"https://www.google.com/maps/preview/review/listentitiesreviews?authuser=0&hl=en&gl=us&pb=!1m2!1y{place_id}!2m2!1i0!3i{limit}!4m5!2b1!3b1!5b1!6b1!7b1"

    headers = {
        "x-api-token": SCRAPELESS_API_KEY,
        "Content-Type": "application/json"
    }

    # Payload matching the 'Unlocker' tool in your Scrapeless dashboard
    payload = {
        "actor": "unlocker.webunlocker",
        "proxy": {
            "country": "ANY"  # Represents 'World Wide'
        },
        "input": {
            "url": target_url,
            "method": "GET"
        }
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            response = await client.post(SCRAPELESS_ENDPOINT, headers=headers, json=payload)
            
            if response.status_code == 200:
                result = response.json()
                raw_content = result.get("content", "")
                
                if not raw_content:
                    return []

                return parse_reviews_json(raw_content)
            else:
                print(f"❌ Scrapeless Error {response.status_code}: {response.text}")
                return []
                
        except Exception as e:
            print(f"⚠️ Network error during Scrapeless request: {e}")
            return []
