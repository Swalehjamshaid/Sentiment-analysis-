import httpx
import json
import logging
import asyncio
import re
from datetime import datetime, timezone
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

async def fetch_reviews(place_id: str, limit: int = 100) -> List[Dict[str, Any]]:
    """
    DUAL-STREAM PROTOCOL:
    Stream A: Surgical Protobuf Extraction (Fast)
    Stream B: Mobile Search Emulation (Resilient)
    """
    all_reviews = []
    
    # 🕵️ Advanced Mobile Headers to mimic a high-end device in Pakistan
    headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
        "Accept": "*/*",
        "Accept-Language": "en-PK,en;q=0.9",
        "Referer": "https://www.google.com.pk/",
        "X-Requested-With": "XMLHttpRequest"
    }

    async with httpx.AsyncClient(headers=headers, timeout=30.0, follow_redirects=True) as client:
        # --- STREAM A: SURGICAL PROTOBUF ---
        # This is the 'Secret Door' that worked for 2 reviews earlier.
        url_a = f"https://www.google.com/search?q=reviews+for+place_id:{place_id}&tbm=map&async=l_rv:1,l_rid:{place_id},l_oc:0,_fmt:json"
        
        try:
            logger.info(f"🛰️ Attempting Stream A for {place_id}...")
            res_a = await client.get(url_a)
            
            if res_a.status_code == 200:
                # Brute-force slice the IDs and Ratings
                chunks = res_a.text.split('["Ch')
                for chunk in chunks[1:]:
                    if len(all_reviews) >= limit: break
                    try:
                        r_id = "Ch" + chunk.split('"')[0]
                        rating_match = re.search(r'\,(\d)\,', chunk)
                        rating = int(rating_match.group(1)) if rating_match else 5
                        
                        # Capture the longest string as the review text
                        texts = [s for s in chunk.split('"') if len(s) > 15]
                        review_text = max(texts, key=len) if texts else "No text"
                        
                        all_reviews.append({
                            "review_id": r_id,
                            "rating": rating,
                            "text": review_text.replace('\\u0027', "'").replace('\\n', ' '),
                            "author": "Verified Customer",
                            "date": datetime.now(timezone.utc).isoformat()
                        })
                    except: continue

            if len(all_reviews) > 0:
                logger.info(f"✅ Stream A Success: {len(all_reviews)} reviews.")
                return all_reviews

        except Exception as e:
            logger.warning(f"⚠️ Stream A Failed: {e}")

        # --- STREAM B: MOBILE SEARCH EMULATION (FALLBACK) ---
        # If Stream A returns 0, we pivot to the direct Search Cluster.
        if not all_reviews:
            logger.info("🔄 Stream A empty. Pivoting to Stream B (Mobile Emulation)...")
            url_b = f"https://www.google.com.pk/maps/preview/review/listentitiesreviews?pb=!1s{place_id}!2i0!3i100!4m5!4b1!5b1!6b1!7b1!5e1"
            
            try:
                res_b = await client.get(url_b)
                if res_b.status_code == 200:
                    raw_text = res_b.text.lstrip(")]}'\n")
                    data = json.loads(raw_text)
                    if data and len(data) > 2 and data[2]:
                        for r in data[2]:
                            all_reviews.append({
                                "review_id": str(r[0]),
                                "rating": int(r[4]),
                                "text": str(r[3]) if r[3] else "No text",
                                "author": "Local Guide",
                                "date": datetime.now(timezone.utc).isoformat()
                            })
            except Exception as e:
                logger.error(f"❌ Stream B Failure: {e}")

    logger.info(f"🚀 Final Result: {len(all_reviews)} reviews.")
    return all_reviews
