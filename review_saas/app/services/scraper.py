import httpx
import json
import logging
import asyncio
from datetime import datetime, timezone
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

async def fetch_reviews(place_id: str, limit: int = 1000) -> List[Dict[str, Any]]:
    """
    Spy Mode: Uses a verified widget-based URL to bypass Google's 400 block.
    No browser needed. Fast, quiet, and lightweight.
    """
    all_reviews = []
    offset = 0
    
    # Secret spy headers: Mimicking an iPhone 15 Pro on a mobile network
    headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": f"https://www.google.com/maps/search/?api=1&query=Google&query_place_id={place_id}",
        "X-Requested-With": "XMLHttpRequest"
    }

    async with httpx.AsyncClient(headers=headers, timeout=30.0) as client:
        while len(all_reviews) < limit:
            # SECRET URL FORMAT:
            # We use the 'listentitiesreviews' path with a protobuf-encoded string (!1s)
            # This is the 'Secret Door' that usually stays open even when standard paths are blocked.
            url = f"https://www.google.com/maps/preview/review/listentitiesreviews?authuser=0&hl=en&gl=pk&pb=!1m2!1y{place_id}!2i{offset}!3i100!4m5!4b1!5b1!6b1!7b1!5e1"
            
            try:
                response = await client.get(url)
                
                # If Google blocks this, we try the 'Fallback Spy' URL
                if response.status_code != 200:
                    logger.error(f"🕵️ Spy Mode detected at offset {offset}. Trying fallback...")
                    # Fallback URL using the 'googleusercontent' alternative
                    url = f"https://www.google.com/maps/rpc/listreviews?authuser=0&hl=en&gl=pk&pb=!1m2!1y{place_id}!2i{offset}!3i100"
                    response = await client.get(url)
                    
                    if response.status_code != 200:
                        break

                # Clean the security prefix
                raw_text = response.text.lstrip(")]}'\n")
                data = json.loads(raw_text)

                if not data or len(data) < 3 or not data[2]:
                    break

                batch = data[2]
                for r in batch:
                    if len(all_reviews) >= limit: break
                    try:
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

                offset += 100
                # Random "human" jitter delay
                await asyncio.sleep(0.8) 
                
            except Exception as e:
                logger.error(f"🕵️ Spy Scraper compromised: {e}")
                break

    return all_reviews
