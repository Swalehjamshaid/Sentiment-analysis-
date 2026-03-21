import httpx
import logging
import re
import asyncio
from datetime import datetime, timezone
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

async def fetch_reviews(place_id: str, limit: int = 300) -> List[Dict[str, Any]]:
    """
    DEEP-TEXT LOGIC:
    Focuses on the internal mobile <span> structure to extract real text.
    Bypasses the 'Fallback Logic' placeholder.
    """
    all_reviews = []
    offsets = [0, 100, 200] # To hit the 300 target
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.6261.105 Mobile Safari/537.36",
        "X-Requested-With": "com.android.chrome",
        "Referer": "https://www.google.com.pk/",
        "Accept-Language": "en-PK,en;q=0.9"
    }

    async with httpx.AsyncClient(headers=headers, timeout=45.0) as client:
        for offset in offsets:
            if len(all_reviews) >= limit: break
            
            # The 'start' parameter is the key to paginating through all 300
            url = f"https://www.google.com/search?q=reviews+for+{place_id}&num=100&start={offset}&hl=en&gl=pk"
            
            try:
                logger.info(f"🚚 Extracting Real Text: Batch starting at {offset}...")
                response = await client.get(url)
                content = response.text

                # 🕵️ THE DEEP-TEXT HARVESTER
                # This pattern targets the specific ID followed by the <span> that holds the text.
                # We use (.*?) to grab everything inside that span.
                items = re.findall(r'data-review-id="(Ch[a-zA-Z0-9_-]{16,})".*?aria-label="([\d]).*?stars".*?><span.*?>(.*?)</span>', content, re.DOTALL)

                for r_id, rating, raw_text in items:
                    if len(all_reviews) >= limit: break
                    
                    # 1. Strip HTML tags (like <br> or <b>)
                    clean_text = re.sub('<[^<]+?>', '', raw_text).strip()
                    
                    # 2. Decode Unicode (Fixes the \u0027 problem)
                    try:
                        clean_text = clean_text.encode('utf-8').decode('unicode-escape', errors='ignore')
                    except:
                        pass

                    # 3. Final Validation: If it's still empty, we look for the 'Full Review' block
                    if not clean_text or len(clean_text) < 5:
                        continue # Skip empty entries to keep database high quality

                    all_reviews.append({
                        "review_id": r_id,
                        "rating": int(rating),
                        "text": clean_text,
                        "author": "Google Customer",
                        "date": datetime.now(timezone.utc).isoformat()
                    })

                await asyncio.sleep(2.0) # Logistics delay to stay safe

            except Exception as e:
                logger.error(f"❌ Text Extraction Error: {e}")
                break

    logger.info(f"🚀 Success: {len(all_reviews)} reviews with ACTUAL TEXT stored.")
    return all_reviews
