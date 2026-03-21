import httpx
import json
import logging
import asyncio
from datetime import datetime, timezone
from typing import List, Dict, Any

# Standard logging for your Railway dashboard
logger = logging.getLogger(__name__)

async def fetch_reviews(place_id: str, limit: int = 1000) -> List[Dict[str, Any]]:
    """
    Final Lightweight Scraper: Drop-in replacement for Playwright.
    Uses httpx to mimic a browser and fetch data directly from Google.
    """
    all_reviews = []
    offset = 0
    page_size = 100 

    # High-authority headers to bypass Google's "400 Bad Request"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.google.com/",
        "Origin": "https://www.google.com",
        "Connection": "keep-alive",
    }

    async with httpx.AsyncClient(headers=headers, timeout=30.0, follow_redirects=True) as client:
        while len(all_reviews) < limit:
            # This specific internal URL format is the most resilient for Lahore-based Place IDs
            url = f"https://www.google.com/maps/preview/review/listentitiesreviews?authuser=0&hl=en&gl=us&pb=!1m1!1s{place_id}!2i{offset}!3i{page_size}!4m5!4b1!5b1!6b1!7b1!5e1"
            
            try:
                response = await client.get(url)
                
                if response.status_code != 200:
                    logger.error(f"❌ Google Blocked Request (Status {response.status_code})")
                    break

                # Strip Google's security prefix: )]}'
                raw_text = response.text.lstrip(")]}'\n")
                
                try:
                    data = json.loads(raw_text)
                except json.JSONDecodeError:
                    logger.error("❌ Failed to parse response JSON.")
                    break

                # Index [2] is where the list of reviews lives in Google's internal API
                if not data or len(data) < 3 or not data[2]:
                    logger.info(f"✅ Reached end of reviews at offset {offset}.")
                    break

                batch = data[2]
                for r in batch:
                    if len(all_reviews) >= limit:
                        break
                    try:
                        # Extracting and converting to explicit types for database safety
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

                # If the batch returned is smaller than requested, we're done
                if len(batch) < page_size:
                    break

                offset += page_size
                
                # Human-like delay to prevent IP flagging (Breaking the Circle of Bans)
                await asyncio.sleep(1.5)
                
            except Exception as e:
                logger.error(f"❌ Critical Scraper Failure: {str(e)}")
                break

    logger.info(f"🚀 Successfully collected {len(all_reviews)} reviews.")
    return all_reviews
