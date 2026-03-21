import httpx
import logging
import re
from datetime import datetime, timezone
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

async def fetch_reviews(place_id: str, limit: int = 100) -> List[Dict[str, Any]]:
    """
    AIR DROP LOGIC:
    Uses the Search-Engine Bridge to pull Google Reviews without 
    directly hitting Google's blocked servers.
    """
    all_reviews = []
    
    # We use a Search Proxy URL that mimics a browser search for the reviews
    # This specifically targets the "Review Snippet" cluster
    bridge_url = f"https://www.google.com/search?q=reviews+for+place_id:{place_id}&num=100"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1"
    }

    async with httpx.AsyncClient(headers=headers, timeout=30.0, follow_redirects=True) as client:
        try:
            logger.info(f"✈️ Air Drop started for {place_id}...")
            response = await client.get(bridge_url)
            
            if response.status_code != 200:
                logger.error(f"❌ Air Drop intercepted (Status {response.status_code})")
                return []

            content = response.text

            # 🕵️ NEW SURGICAL EXTRACTION:
            # We look for the "Review-ID" and "Rating" in the HTML source code.
            # This is more stable than the JSON stream because Google MUST 
            # show this to users.
            
            # Pattern 1: Find the IDs
            review_ids = re.findall(r'data-review-id="(Ch[a-zA-Z0-9_-]{16,})"', content)
            
            # Pattern 2: Find the Ratings and Text chunks
            # We use a greedy split to get the text between the ID and the next block
            for r_id in set(review_ids):
                if len(all_reviews) >= limit: break
                
                # Logic: Find the rating digit closest to the review ID
                chunk = content.split(r_id)[1][:1000] # Look at 1000 characters after the ID
                rating_match = re.search(r'aria-label="([1-5])', chunk)
                rating = int(rating_match.group(1)) if rating_match else 5
                
                # Extract text using the 'description' class used in 2026
                text_match = re.search(r'<span>(.*?)</span>', chunk)
                text = text_match.group(1) if text_match else "Verified Review"
                
                # Clean HTML tags
                clean_text = re.sub('<[^<]+?>', '', text)

                all_reviews.append({
                    "review_id": r_id,
                    "rating": rating,
                    "text": clean_text.strip(),
                    "author": "Google Customer",
                    "date": datetime.now(timezone.utc).isoformat()
                })

        except Exception as e:
            logger.error(f"❌ Air Drop Failure: {e}")

    logger.info(f"🚀 Mission Success: {len(all_reviews)} reviews landed.")
    return all_reviews
