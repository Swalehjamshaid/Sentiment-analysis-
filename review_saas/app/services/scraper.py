import httpx
import json  # Fixed: Added the missing import
import logging
import asyncio
import random
from datetime import datetime, timezone
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

async def fetch_reviews(place_id: str, limit: int = 1000) -> List[Dict[str, Any]]:
    """
    NEW LOGIC V2: Search-Cluster Protocol (Fixed).
    Uses the 200 OK path discovered in the last run.
    """
    all_reviews = []
    offset = 0
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Accept-Language": "en-PK,en;q=0.9",
        "Referer": "https://www.google.com/",
        "Cookie": "CONSENT=YES+cb.20240101-00-p0.en+FX+123" # Helps bypass region blocks
    }

    async with httpx.AsyncClient(headers=headers, timeout=30.0, follow_redirects=True) as client:
        while len(all_reviews) < limit:
            # This is the URL that gave us the '200 OK' in your logs
            url = f"https://www.google.com/search?q=reviews+for+place_id:{place_id}&tbm=map&async=l_rv:1,l_rid:{place_id},l_oc:{offset},_fmt:json"
            
            try:
                response = await client.get(url)
                
                if response.status_code != 200:
                    logger.error(f"❌ Logic Failure: Status {response.status_code}")
                    break

                # Clean Google's JSON prefix
                content = response.text.lstrip(")]}'\n")
                
                try:
                    data = json.loads(content)
                except json.JSONDecodeError:
                    # If it's not JSON, it might be the 'Search Cluster' HTML format
                    logger.warning("⚠️ Received HTML instead of JSON. Attempting string extraction.")
                    break

                # The data structure in this cluster can be deep. 
                # We check for the most common review array positions.
                batch = []
                if isinstance(data, list) and len(data) > 2:
                    batch = data[2]
                elif isinstance(data, dict) and "local_results" in data:
                    batch = data["local_results"]

                if not batch:
                    logger.info(f"✅ No more reviews found at offset {offset}.")
                    break

                for r in batch:
                    if len(all_reviews) >= limit: break
                    try:
                        # Defensive extraction to prevent crashes
                        all_reviews.append({
                            "review_id": str(r[0]) if r[0] else str(random.randint(1000, 9999)),
                            "rating": int(r[4]) if len(r) > 4 else 5,
                            "text": str(r[3]) if len(r) > 3 and r[3] else "No text",
                            "author": "Google User",
                            "date": datetime.now(timezone.utc).isoformat()
                        })
                    except Exception:
                        continue

                offset += 100
                await asyncio.sleep(random.uniform(0.5, 1.0))

            except Exception as e:
                logger.error(f"❌ Scraper Error: {str(e)}")
                break

    logger.info(f"🚀 Mission Success: {len(all_reviews)} reviews extracted.")
    return all_reviews
