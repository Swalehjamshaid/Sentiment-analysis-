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
    REGIONAL STEALTH V3: 
    Uses the .com.pk domain to bypass regional 400 errors.
    This is the most stable 'Spy' method for Lahore-based targets.
    """
    all_reviews = []
    offset = 0
    
    # 🕵️ Mobile Agent from a local Pakistan perspective
    headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
        "Accept": "*/*",
        "Accept-Language": "en-PK,en;q=0.9",
        "Referer": "https://www.google.com.pk/",
        "X-Requested-With": "XMLHttpRequest"
    }

    async with httpx.AsyncClient(headers=headers, timeout=30.0, follow_redirects=True) as client:
        while len(all_reviews) < limit:
            # THE FIX: We use https://www.google.com.pk instead of googleusercontent
            # The 'pb' string is the internal Google Protobuf format
            url = f"https://www.google.com.pk/maps/preview/review/listentitiesreviews?authuser=0&hl=en&gl=pk&pb=!1s{place_id}!2i{offset}!3i100!4m5!4b1!5b1!6b1!7b1!5e1"
            
            try:
                response = await client.get(url)
                
                # If we get a 400 here, it means the Place ID format is slightly off
                if response.status_code != 200:
                    logger.error(f"🕵️ Regional Wall hit (Status {response.status_code}). Breaking circle.")
                    break

                # Strip JSON security prefix: )]}'
                raw_text = response.text.lstrip(")]}'\n")
                data = json.loads(raw_text)

                if not data or len(data) < 3 or not data[2]:
                    logger.info(f"✅ Mission Success: No more reviews at {offset}")
                    break

                batch = data[2]
                for r in batch:
                    if len(all_reviews) >= limit: break
                    try:
                        all_reviews.append({
                            "review_id": str(r[0]),
                            "rating": int(r[4]),
                            "text": str(r[3]) if r[3] else "",
                            "author": str(r[1][4][0][4]) if (len(r) > 1 and r[1]) else "Local User",
                            "timestamp_ms": r[27],
                            "date": datetime.fromtimestamp(r[27]/1000, tz=timezone.utc).isoformat()
                        })
                    except (IndexError, TypeError):
                        continue

                offset += 100
                # Human-like delay
                await asyncio.sleep(random.uniform(0.5, 1.0)) 
                
            except Exception as e:
                logger.error(f"🕵️ Scraper Failure: {e}")
                break

    return all_reviews
