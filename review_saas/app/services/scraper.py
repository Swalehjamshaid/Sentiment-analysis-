import httpx
import json
import logging
import asyncio
import random
from datetime import datetime, timezone
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

# 🔑 ACTION: Get your free key at scraperapi.com (5,000 free credits)
SCRAPER_API_KEY = "REPLACE_WITH_YOUR_SCRAPERAPI_KEY"

async def fetch_reviews(place_id: str, limit: int = 100) -> List[Dict[str, Any]]:
    """
    INTERNATIONAL SUCCESS LOGIC:
    Uses a Global Proxy Carrier (ScraperAPI) with automatic regional fallback.
    Bypasses data-center blocks (Railway) by routing through residential IPs.
    """
    all_reviews = []
    
    # The standard Google data node URL
    target_url = f"https://www.google.com/maps/preview/review/listentitiesreviews?pb=!1s{place_id}!2i0!3i100!4m5!4b1!5b1!6b1!7b1!5e1"
    
    # We cycle through major international hubs if the first attempt fails
    countries = ["us", "gb", "de", "jp", "pk"]
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        for country in countries:
            logger.info(f"🌍 International Attempt: Routing through {country.upper()}...")
            
            proxy_params = {
                "api_key": SCRAPER_API_KEY,
                "url": target_url,
                "country_code": country,
                "device_type": "mobile",
                "render": "false" # Fast, raw data mode
            }

            try:
                response = await client.get("http://api.scraperapi.com", params=proxy_params)
                
                if response.status_code == 200:
                    # Clean the JSON security prefix
                    raw_text = response.text.lstrip(")]}'\n")
                    data = json.loads(raw_text)

                    if data and len(data) > 2 and data[2]:
                        batch = data[2]
                        for r in batch:
                            if len(all_reviews) >= limit: break
                            try:
                                all_reviews.append({
                                    "review_id": str(r[0]),
                                    "rating": int(r[4]),
                                    "text": str(r[3]) if r[3] else "No text provided",
                                    "author": "Global Reviewer",
                                    "date": datetime.now(timezone.utc).isoformat()
                                })
                            except (IndexError, TypeError):
                                continue
                        
                        if all_reviews:
                            logger.info(f"✅ Success! Pulled {len(all_reviews)} reviews via {country.upper()}.")
                            return all_reviews # Exit early once we have the data
                
                logger.warning(f"⚠️ {country.upper()} node returned no data. Trying next region...")
                
            except Exception as e:
                logger.error(f"❌ Connection error on {country.upper()} node: {e}")
                continue
                
            # Small delay between regional hops to avoid fingerprinting
            await asyncio.sleep(1)

    logger.error("🚫 All international nodes exhausted. Check ScraperAPI credits.")
    return []
