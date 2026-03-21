import httpx
import json
import logging
import asyncio
import random
import re
from datetime import datetime, timezone
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

async def fetch_reviews(place_id: str, limit: int = 1000) -> List[Dict[str, Any]]:
    """
    VOLUME BOOSTER: Relaxed Surgical Extraction.
    Now that we have 200 OK, we widen the 'net' to catch every review in the stream.
    """
    all_reviews = []
    offset = 0
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Referer": "https://www.google.com.pk/",
    }

    async with httpx.AsyncClient(headers=headers, timeout=20.0) as client:
        while len(all_reviews) < limit:
            url = f"https://www.google.com/search?q=reviews+for+place_id:{place_id}&tbm=map&async=l_rv:1,l_rid:{place_id},l_oc:{offset},_fmt:json"
            
            try:
                response = await client.get(url)
                if response.status_code != 200: break

                raw_data = response.text
                
                # 🕵️ RELAXED PATTERN: Find the Review ID (Ch...) and everything until the next one
                # This ensures we don't miss reviews with complex formatting
                chunks = re.split(r'\["(Ch[a-zA-Z0-9_-]{15,})"', raw_data)[1:]
                
                if not chunks:
                    break

                # Process chunks in pairs (ID, then the data following it)
                for i in range(0, len(chunks), 2):
                    if len(all_reviews) >= limit: break
                    r_id = chunks[i]
                    chunk_data = chunks[i+1] if i+1 < len(chunks) else ""
                    
                    try:
                        # Find the first digit (1-5) after the ID - that's the rating
                        rating_match = re.search(r'\,(\d)\,', chunk_data)
                        rating = int(rating_match.group(1)) if rating_match else 5
                        
                        # Find the longest string in quotes - that's the review text
                        texts = re.findall(r'"([^"]{5,})"', chunk_data)
                        review_text = max(texts, key=len) if texts else "No text provided"
                        
                        # Clean unicode
                        clean_text = review_text.encode('utf-8').decode('unicode-escape', errors='ignore')
                        
                        all_reviews.append({
                            "review_id": r_id,
                            "rating": rating,
                            "text": clean_text,
                            "author": "Local Guide",
                            "date": datetime.now(timezone.utc).isoformat()
                        })
                    except:
                        continue

                # Move to next page
                if len(chunks) < 10: break 
                offset += 100
                await asyncio.sleep(0.5)

            except Exception as e:
                logger.error(f"❌ Volume Booster Error: {e}")
                break

    logger.info(f"🚀 Mission Accomplished: {len(all_reviews)} reviews pulled.")
    return all_reviews
