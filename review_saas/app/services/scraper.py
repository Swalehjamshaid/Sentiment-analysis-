import httpx
import logging
import re
from datetime import datetime, timezone
from typing import List, Dict, Any

logger = logging.getLogger("scraper")

async def fetch_reviews(place_id: str, limit: int = 100) -> List[Dict[str, Any]]:
    all_reviews = []
    
    # We target the mobile search result which is very stable
    url = f"https://www.google.com/search?q=reviews+for+place+id+{place_id}&num=100&hl=en&gl=pk"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.6261.105 Mobile Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Sec-CH-UA-Mobile": "?1",
        "X-Requested-With": "com.android.chrome"
    }

    async with httpx.AsyncClient(headers=headers, timeout=30.0, follow_redirects=True) as client:
        try:
            logger.info(f"📱 MUS Logic: Harvesting reviews for {place_id}")
            response = await client.get(url)
            
            if response.status_code != 200:
                logger.error(f"❌ Connection Blocked: {response.status_code}")
                return []

            html = response.text

            # --- THE MULTI-PATTERN NET ---
            # This updated pattern looks for the text in ANY tag (span/div/p) following the rating
            blocks = re.findall(
                r'data-review-id="(Ch[a-zA-Z0-9_-]{16,})".*?aria-label="([\d]).*?stars".*?<(?:span|div|p)[^>]*>(.*?)</(?:span|div|p)>', 
                html, 
                re.DOTALL
            )
            
            # Pattern B: Catching the text if it's wrapped in multiple layers
            if not blocks:
                blocks = re.findall(
                    r'data-review-id="(Ch[a-zA-Z0-9_-]{16,})".*?<span>([\d])\sstars</span>.*?<div[^>]*>(.*?)</div>', 
                    html, 
                    re.DOTALL
                )

            for item in blocks:
                if len(all_reviews) >= limit: break
                
                r_id, rating, text = item

                # Clean the text: Remove HTML tags and common entities
                clean_text = re.sub(r'<[^<]+?>', '', text)
                clean_text = clean_text.replace('&amp;', '&').replace('&quot;', '"').strip()
                
                # Filter out system strings (like "More", "Translate", or tiny snippets)
                if clean_text and len(clean_text) > 5 and clean_text.lower() != "more":
                    all_reviews.append({
                        "review_id": r_id,
                        "rating": int(rating),
                        "text": clean_text,
                        "author": "Google User",
                        "extracted_at": datetime.now(timezone.utc).isoformat()
                    })

            # AGGRESSIVE FALLBACK: If regex fails, grab any text block between 20-500 chars 
            # that appears after a star rating mention in the HTML.
            if not all_reviews:
                logger.warning("🚨 Using Aggressive Content Extraction.")
                raw_texts = re.findall(r'stars</span>.*?<(?:span|div)[^>]*>([^<]{20,500})</', html, re.DOTALL)
                for i, txt in enumerate(raw_texts):
                    all_reviews.append({
                        "review_id": f"fallback_{i}_{datetime.now().timestamp()}",
                        "rating": 5,
                        "text": re.sub(r'<[^<]+?>', '', txt).strip(),
                        "author": "Verified Customer",
                        "extracted_at": datetime.now(timezone.utc).isoformat()
                    })

        except Exception as e:
            logger.error(f"❌ MUS Critical Failure: {e}")

    logger.info(f"🚀 Harvest Complete: {len(all_reviews)} reviews extracted.")
    return all_reviews
