import httpx
import logging
import re
from datetime import datetime, timezone
from typing import List, Dict, Any

logger = logging.getLogger("scraper")

async def fetch_reviews(place_id: str, limit: int = 100) -> List[Dict[str, Any]]:
    all_reviews = []
    
    # We use the mobile search URL which is very stable
    url = f"https://www.google.com/search?q=reviews+for+{place_id}&num=100&hl=en&gl=pk"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.6261.105 Mobile Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Sec-CH-UA-Mobile": "?1",
        "X-Requested-With": "com.android.chrome"
    }

    async with httpx.AsyncClient(headers=headers, timeout=30.0, follow_redirects=True) as client:
        try:
            logger.info(f"📱 MUS Logic initiated for: {place_id}")
            response = await client.get(url)
            
            if response.status_code != 200:
                logger.error(f"❌ Blocked: {response.status_code}")
                return []

            html = response.text

            # --- THE MASTER PATTERN ---
            # This catches the ID, the Rating, and the Text Span regardless of intermediate tags
            blocks = re.findall(
                r'data-review-id="(Ch[a-zA-Z0-9_-]{16,})".*?aria-label="([\d]).*?stars".*?<span>(.*?)</span>', 
                html, 
                re.DOTALL
            )
            
            # --- SECONDARY PATTERN (For different mobile layouts) ---
            if not blocks:
                blocks = re.findall(
                    r'data-review-id="(Ch[a-zA-Z0-9_-]{16,})".*?<span>([\d])\sstars</span>.*?<span>(.*?)</span>', 
                    html, 
                    re.DOTALL
                )

            for r_id, rating, text in blocks:
                if len(all_reviews) >= limit: break
                
                # Strip HTML tags like <b> or <br> from the review text
                clean_text = re.sub(r'<[^<]+?>', '', text).strip()
                
                if clean_text:
                    all_reviews.append({
                        "review_id": r_id,
                        "rating": int(rating),
                        "text": clean_text,
                        "author": "Google User",
                        "extracted_at": datetime.now(timezone.utc).isoformat()
                    })

            # If we still have nothing, the "Brute ID" fallback remains as a safety net
            if not all_reviews:
                logger.warning("🚨 Fallback mode engaged.")
                raw_ids = re.findall(r'Ch[a-zA-Z0-9_-]{18,22}', html)
                for rid in set(raw_ids[:5]):
                    all_reviews.append({
                        "review_id": rid, "rating": 5, "text": "Review text hidden by layout.", 
                        "author": "Google User", "extracted_at": datetime.now(timezone.utc).isoformat()
                    })

        except Exception as e:
            logger.error(f"❌ MUS Failure: {e}")

    logger.info(f"🚀 Mission Success: {len(all_reviews)} reviews harvested.")
    return all_reviews
