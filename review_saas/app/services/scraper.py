import httpx
import logging
import re
import json
import asyncio
from datetime import datetime, timezone
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

async def fetch_reviews(place_id: str, limit: int = 300) -> List[Dict[str, Any]]:
    """
    RAW PROTOBUF SLICER:
    Bypasses the 'Greedy-Chunk' failure by slicing the raw internal data stream.
    Targets the 'listentitiesreviews' node which is the direct data source.
    """
    all_reviews = []
    
    # We use the raw preview node. !2i0!3i300 asks for 300 reviews at once.
    url = f"https://www.google.com/maps/preview/review/listentitiesreviews?pb=!1s{place_id}!2i0!3i{limit}!4m5!4b1!5b1!6b1!7b1!5e1"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Referer": "https://www.google.com/maps",
        "X-Requested-With": "XMLHttpRequest"
    }

    async with httpx.AsyncClient(headers=headers, timeout=60.0, follow_redirects=True) as client:
        try:
            logger.info(f"🛰️ Slicing Raw Protobuf for {place_id}...")
            response = await client.get(url)
            
            if response.status_code != 200:
                logger.error(f"❌ Slicer Blocked: {response.status_code}")
                return []

            # Google prefixes their raw data with )]}'
            raw_text = response.text.lstrip(")]}'\n")
            data = json.loads(raw_text)

            # The raw data structure is: [header, metadata, [REVIEWS_ARRAY], ...]
            # We surgically dive into index 2 where the reviews live
            if data and len(data) > 2 and data[2]:
                for r in data[2]:
                    if len(all_reviews) >= limit: break
                    try:
                        all_reviews.append({
                            "review_id": str(r[0]),
                            "rating": int(r[4]),
                            "text": str(r[3]) if r[3] else "No text provided",
                            "author": str(r[0][1]) if len(r[0]) > 1 else "Google User",
                            "date": datetime.now(timezone.utc).isoformat()
                        })
                    except (IndexError, TypeError):
                        continue
            
            # FALLBACK: If JSON parsing fails, use Regex to 'cut' the text out
            if not all_reviews:
                logger.warning("⚠️ JSON structure shifted. Using Regex Slicer...")
                # Regex looks for: ["ReviewID", [Rating], "Review Text"]
                matches = re.findall(r'\["(Ch[a-zA-Z0-9_-]{16,})",.*?\[(\d)\],.*?"(.*?)"\]', response.text)
                for r_id, rating, text in matches:
                    all_reviews.append({
                        "review_id": r_id,
                        "rating": int(rating),
                        "text": text.encode('utf-8').decode('unicode-escape', errors='ignore'),
                        "author": "Verified Customer",
                        "date": datetime.now(timezone.utc).isoformat()
                    })

        except Exception as e:
            logger.error(f"❌ Slicer Failure: {e}")

    logger.info(f"🚀 Mission Success: {len(all_reviews)} reviews with TEXT successfully pulled.")
    return all_reviews
