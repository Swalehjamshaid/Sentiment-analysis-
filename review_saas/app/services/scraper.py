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
    Lightweight Stealth Scraper: 100% Python based.
    Bypasses the 'Status 400' error by using professional headers and internal endpoints.
    Matches your project's call: fetch_reviews(place_id, limit)
    """
    all_reviews = []
    offset = 0
    page_size = 100 

    # Professional headers to mimic a real desktop browser
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.google.com/",
        "Origin": "https://www.google.com",
        "Connection": "keep-alive",
    }

    # Using an Async Client for high performance on Railway
    async with httpx.AsyncClient(headers=headers, timeout=30.0, follow_redirects=True) as client:
        while len(all_reviews) < limit:
            # Internal Google Search Review Endpoint
            # This format is highly resilient against 400 Bad Request errors for Lahore-based businesses
            url = f"https://www.google.com/maps/preview/review/listentitiesreviews?authuser=0&hl=en&gl=us&pb=!1m1!1s{place_id}!2i{offset}!3i{page_size}!4m5!4b1!5b1!6b1!7b1!5e1"
            
            try:
                response = await client.get(url)
                
                # Check for blocking
                if response.status_code != 200:
                    logger.error(f"❌ Google Blocked Request. Status: {response.status_code}")
                    break

                # Strip Google's JSON security prefix: )]}'
                raw_text = response.text.lstrip(")]}'\n")
                
                try:
                    data = json.loads(raw_text)
                except json.JSONDecodeError:
                    logger.error("❌ Failed to parse Google JSON response.")
                    break

                # Ensure data exists in the expected Protobuf index [2]
                if not data or len(data) < 3 or not data[2]:
                    logger.info(f"✅ Collection finished at offset {offset}.")
                    break

                batch = data[2]
                for r in batch:
                    if len(all_reviews) >= limit:
                        break
                    try:
                        # Converting to explicit types ensures database safety
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

                # If the batch returned is less than the page size, we've hit the end
                if len(batch) < page_size:
                    break

                offset += page_size
                
                # Human-mimicry delay to prevent IP flagging
                await asyncio.sleep(1.0)
                
            except Exception as e:
                logger.error(f"❌ Scraper Failure: {str(e)}")
                break

    logger.info(f"🚀 Successfully scraped {len(all_reviews)} reviews for {place_id}")
    return all_reviews
