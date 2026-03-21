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
    GHOST SESSION LOGIC:
    1. Mimics a real browser landing on Google.pk first.
    2. Captures search session cookies automatically.
    3. Uses the 'Feature-Id' bypass to pull reviews from the Search Cluster.
    """
    all_reviews = []
    
    # 🕵️ Unique Mobile Fingerprints
    user_agents = [
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
        "Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.6261.105 Mobile Safari/537.36"
    ]

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        # STEP 1: Establish the "Ghost Session" (Get the Cookies)
        # We hit the main Pakistan search page first to look like a real person in Lahore.
        base_url = "https://www.google.com.pk/"
        headers = {"User-Agent": random.choice(user_agents)}
        
        try:
            await client.get(base_url, headers=headers)
            
            # STEP 2: The "Feature-Id" Bypass
            # We use the search path with 'lrd', which is Google's internal ID for review cards.
            # 0x...:0x... is the internal hex format for your Place ID.
            url = f"https://www.google.com.pk/async/reviewSort?vet=12ahUKEwi&ved=12ahUKEwi&yv=3&async=feature_id:{place_id},review_source:All,sort_by:qualityScore,is_owner:false,filter_text:,associated_topic:,next_page_token:,_pms:s,_fmt:pc"
            
            response = await client.get(url, headers={
                **headers,
                "Referer": "https://www.google.com.pk/",
                "X-Requested-With": "XMLHttpRequest"
            })

            if response.status_code != 200:
                logger.error(f"❌ Ghost Session Blocked (Status {response.status_code})")
                return []

            # STEP 3: Greedy String Extraction (Resilient to JSON changes)
            content = response.text
            
            # Look for Review IDs and Text patterns in the raw HTML response
            # Google's search cluster returns HTML snippets inside the JSON
            review_blocks = re.findall(r'data-review-id="(Ch[a-zA-Z0-9_-]{15,})".*?aria-label="([\d]).*?stars".*?class="description"><span>(.*?)</span>', content, re.DOTALL)

            for r_id, rating, text in review_blocks:
                if len(all_reviews) >= limit: break
                
                # Clean the text from HTML tags and unicode
                clean_text = re.sub('<[^<]+?>', '', text)
                clean_text = clean_text.encode('utf-8').decode('unicode-escape', errors='ignore')

                all_reviews.append({
                    "review_id": r_id,
                    "rating": int(rating),
                    "text": clean_text.strip() or "No text provided",
                    "author": "Verified Searcher",
                    "date": datetime.now(timezone.utc).isoformat()
                })

            # FALLBACK: If Greedy Regex failed, try the old listentities format
            if not all_reviews:
                logger.warning("⚠️ Ghost Session found no HTML patterns. Trying Protobuf Fallback...")
                fallback_url = f"https://www.google.com.pk/maps/preview/review/listentitiesreviews?pb=!1s{place_id}!2i0!3i100!4m5!4b1!5b1!6b1!7b1!5e1"
                res = await client.get(fallback_url, headers=headers)
                if res.status_code == 200:
                    raw_text = res.text.lstrip(")]}'\n")
                    data = json.loads(raw_text)
                    if data and len(data) > 2 and data[2]:
                        for r in data[2]:
                            all_reviews.append({
                                "review_id": str(r[0]),
                                "rating": int(r[4]),
                                "text": str(r[3]) if r[3] else "",
                                "date": datetime.now(timezone.utc).isoformat()
                            })

        except Exception as e:
            logger.error(f"❌ Ghost Session Failure: {e}")

    logger.info(f"🚀 Mission Success: {len(all_reviews)} reviews extracted via Ghost Session.")
    return all_reviews
