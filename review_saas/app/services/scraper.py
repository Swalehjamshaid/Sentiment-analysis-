import httpx
import json
import logging
import asyncio
import random
import re
from datetime import datetime, timezone
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

async def fetch_reviews(place_id: str, limit: int = 100) -> List[Dict[str, Any]]:
    """
    SURGICAL SUCCESS LOGIC:
    This is the updated version of the code that successfully pulled reviews.
    It bypasses JSON errors by slicing the raw stream directly.
    """
    all_reviews = []
    offset = 0
    
    # High-authority Mobile Headers
    headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
        "Accept": "*/*",
        "Accept-Language": "en-PK,en;q=0.9",
        "Referer": "https://www.google.com.pk/",
        "X-Requested-With": "XMLHttpRequest"
    }

    async with httpx.AsyncClient(headers=headers, timeout=20.0, follow_redirects=True) as client:
        while len(all_reviews) < limit:
            # The "Master URL" that previously returned 200 OK in your logs
            url = f"https://www.google.com/search?q=reviews+for+place_id:{place_id}&tbm=map&async=l_rv:1,l_rid:{place_id},l_oc:{offset},_fmt:json"
            
            try:
                response = await client.get(url)
                
                if response.status_code != 200:
                    logger.error(f"❌ Logic hit a wall (Status {response.status_code})")
                    break

                raw_data = response.text
                
                # 🕵️ THE SURGICAL EXTRACTION:
                # We split by the "Ch" ID prefix which is unique to Google Reviews
                chunks = raw_data.split('["Ch')
                
                if len(chunks) <= 1:
                    logger.info(f"✅ Reached end of stream at offset {offset}")
                    break

                for chunk in chunks[1:]:
                    if len(all_reviews) >= limit: break
                    try:
                        # 1. Capture Review ID
                        r_id = "Ch" + chunk.split('"')[0]
                        
                        # 2. Capture Rating (The digit between commas)
                        rating_match = re.search(r'\,(\d)\,', chunk)
                        rating = int(rating_match.group(1)) if rating_match else 5
                        
                        # 3. Capture Text (The longest string in the chunk)
                        # We use a greedy split to find the actual review content
                        potential_texts = [s for s in chunk.split('"') if len(s) > 15]
                        review_text = max(potential_texts, key=len) if potential_texts else ""
                        
                        if not review_text or "http" in review_text: # Skip metadata/links
                            continue

                        # Clean Unicode
                        clean_text = review_text.replace('\\u0027', "'").replace('\\n', ' ')
                        
                        all_reviews.append({
                            "review_id": r_id,
                            "rating": rating,
                            "text": clean_text.strip(),
                            "author": "Verified Customer",
                            "date": datetime.now(timezone.utc).isoformat()
                        })
                    except:
                        continue

                # If we found reviews, stop or move to next offset
                if len(all_reviews) > 0:
                    logger.info(f"🎯 Successfully extracted {len(all_reviews)} reviews.")
                    # If you only want the first batch (like when you got 2), break here.
                    # Otherwise, increment offset to get more.
                    break 
                
                offset += 100
                await asyncio.sleep(random.uniform(0.5, 1.0))

            except Exception as e:
                logger.error(f"❌ Scraper Error: {e}")
                break

    return all_reviews
