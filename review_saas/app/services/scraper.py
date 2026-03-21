import httpx
import json
import logging
import asyncio
import random
from datetime import datetime, timezone
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

async def fetch_reviews(place_id: str, limit: int = 1000) -> List[Dict[str, Any]]:
    """
    Super Spy Mode: Uses high-authority mobile headers and regional flags
    to bypass Google's 400 block. Fast, quiet, and lightweight.
    """
    all_reviews = []
    offset = 0
    
    # 🕵️ Stealth Headers: Mimicking a premium mobile device in Pakistan
    headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
        "Accept": "*/*",
        "Accept-Language": "en-PK,en-US;q=0.9,en;q=0.8",
        "Referer": "https://www.google.com/",
        "X-Requested-With": "XMLHttpRequest",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin"
    }

    async with httpx.AsyncClient(headers=headers, timeout=30.0, follow_redirects=True) as client:
        while len(all_reviews) < limit:
            # THE SECRET PATH: 
            # gl=pk (Pakistan) and hl=en (English) help align with your Lahore target
            # !1s is the protobuf key for the Place ID
            url = f"https://www.google.com/maps/preview/review/listentitiesreviews?authuser=0&hl=en&gl=pk&pb=!1m2!1y{place_id}!2i{offset}!3i100!3e1!4m5!4b1!5b1!6b1!7b1!5e1"
            
            try:
                response = await client.get(url)
                
                # Check for blocking
                if response.status_code != 200:
                    logger.error(f"🕵️ Spy Mode hit a wall at offset {offset} (Status {response.status_code}).")
                    # Immediate Fallback to the alternate data-node
                    url_fallback = f"https://www.google.com/maps/api/place/js/PhotoService.GetReviews?pb=!1m2!1y{place_id}!2i{offset}!3i100"
                    response = await client.get(url_fallback)
                    
                    if response.status_code != 200:
                        break

                # Clean the security prefix Google adds to JSON
                raw_text = response.text.lstrip(")]}'\n")
                
                try:
                    data = json.loads(raw_text)
                except json.JSONDecodeError:
                    logger.error("❌ Failed to parse spy data. Google changed the format.")
                    break

                # Index [2] contains the review array in Google's internal API
                if not data or len(data) < 3 or not data[2]:
                    logger.info(f"✅ Mission complete. No more reviews found at offset {offset}.")
                    break

                batch = data[2]
                for r in batch:
                    if len(all_reviews) >= limit:
                        break
                    try:
                        # Extracting with surgical precision
                        all_reviews.append({
                            "review_id": str(r[0]),
                            "rating": int(r[4]),
                            "text": str(r[3]) if r[3] else "",
                            "author": str(r[1][4][0][4]) if (len(r) > 1 and r[1]) else "Anonymous",
                            "timestamp_ms": r[27],
                            "date": datetime.fromtimestamp(r[27]/1000, tz=timezone.utc).isoformat()
                        })
                    except (IndexError, TypeError):
                        continue

                # If the batch is smaller than 100, we've reached the end
                if len(batch) < 100:
                    break

                offset += 100
                
                # Random Jitter: Acting human to avoid IP bans
                await asyncio.sleep(random.uniform(0.5, 1.2))
                
            except Exception as e:
                logger.error(f"🕵️ Spy Scraper compromised: {e}")
                break

    logger.info(f"🚀 Successfully extracted {len(all_reviews)} reviews.")
    return all_reviews
