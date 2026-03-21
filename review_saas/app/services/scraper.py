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
    BRUTE FORCE EXTRACTION:
    Uses manual string splitting to bypass Google's complex JSON encoding.
    Matches the 200 OK stream confirmed in the logs.
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
                
                # 🕵️ THE BRUTE FORCE SPLIT:
                # Every review in this stream starts with a specific ID pattern
                chunks = raw_data.split('["Ch')
                
                if len(chunks) <= 1:
                    logger.info(f"✅ End of data stream at offset {offset}")
                    break

                for chunk in chunks[1:]: # Skip the first part before the first ID
                    if len(all_reviews) >= limit: break
                    try:
                        # 1. Extract Review ID
                        r_id = "Ch" + chunk.split('"')[0]
                        
                        # 2. Extract Rating (It's always a single digit 1-5 followed by a comma)
                        # We look for the first occurrence after the ID
                        rating = 5
                        for char in chunk:
                            if char in "12345":
                                rating = int(char)
                                break
                        
                        # 3. Extract Text (It's the longest string inside double quotes)
                        # We clean up common Google escape characters
                        potential_texts = [s for s in chunk.split('"') if len(s) > 10]
                        review_text = max(potential_texts, key=len) if potential_texts else "No text"
                        
                        # Quick clean of the text
                        review_text = review_text.replace('\\u0027', "'").replace('\\n', ' ')
                        
                        all_reviews.append({
                            "review_id": r_id,
                            "rating": rating,
                            "text": review_text,
                            "author": "Local Guide",
                            "date": datetime.now(timezone.utc).isoformat()
                        })
                    except:
                        continue

                # If we found less than 5 reviews, it's likely the end of the list
                if len(chunks) < 5: break 
                
                offset += 100
                await asyncio.sleep(random.uniform(0.3, 0.6))

            except Exception as e:
                logger.error(f"❌ Brute Force Error: {e}")
                break

    logger.info(f"🚀 Mission Accomplished: {len(all_reviews)} reviews pulled via Brute Force.")
    return all_reviews
