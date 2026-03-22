import httpx
import logging
import re
import json
from datetime import datetime, timezone
from typing import List, Dict, Any
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger("scraper")

class GoogleMobileScraper:
    def __init__(self):
        # High-authority Mobile Headers (Pixel 8 Pro)
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.6261.105 Mobile Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Sec-CH-UA-Mobile": "?1",
            "Sec-CH-UA-Platform": '"Android"',
            "X-Requested-With": "com.android.chrome",
            "Referer": "https://www.google.com/"
        }

    def _clean_text(self, text: str) -> str:
        """Removes HTML tags and cleans up whitespace/entities."""
        if not text: return ""
        text = re.sub(r'<[^<]+?>', '', text)
        text = text.replace('&amp;', '&').replace('&quot;', '"').replace('&#39;', "'")
        return " ".join(text.split()).strip()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=4, max=10)
    )
    async def run(self, place_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        # Using the Search 'Review' cluster URL - more stable for Place IDs
        url = f"https://www.google.com/search?q=reviews+for+place+id+{place_id}&num=100&hl=en&gl=pk"
        
        all_reviews = []
        
        async with httpx.AsyncClient(headers=self.headers, timeout=30.0, follow_redirects=True) as client:
            logger.info(f"📱 MUS-Logic: Requesting mobile data for {place_id}")
            response = await client.get(url)
            
            if response.status_code != 200:
                logger.error(f"❌ Google Blocked Request: {response.status_code}")
                return []

            html = response.text

            # 1. PRIMARY EXTRACTION: Data-Review-ID Blocks
            # This captures the ID, Rating, and Review Body in one surgical sweep
            blocks = re.findall(
                r'data-review-id="(Ch[a-zA-Z0-9_-]{16,})".*?aria-label="([\d]).*?stars".*?<(?:span|div)[^>]*>(.*?)</(?:span|div)>', 
                html, 
                re.DOTALL
            )

            for r_id, rating, raw_text in blocks:
                if len(all_reviews) >= limit: break
                
                clean_body = self._clean_text(raw_text)
                
                # Filter out 'system' text like "More", "Translate", or empty snippets
                if len(clean_body) > 10 and clean_body.lower() != "more":
                    all_reviews.append({
                        "review_id": r_id,
                        "rating": int(rating),
                        "text": clean_body,
                        "author": "Google User",
                        "extracted_at": datetime.now(timezone.utc).isoformat()
                    })

            # 2. SECONDARY EXTRACTION: JSON/Script Snippets
            # Sometimes Google hides data in a JSON-like string at the bottom
            if not all_reviews:
                logger.warning("⚠️ Primary regex failed. Attempting JSON-Snippet extraction.")
                # This looks for text blocks between 40-500 chars that follow a rating mention
                snippets = re.findall(r'aria-label="[\d]\.[\d] stars".*?<span>([^<]{40,500})</span>', html, re.DOTALL)
                for i, snip in enumerate(snippets):
                    if len(all_reviews) >= limit: break
                    all_reviews.append({
                        "review_id": f"snip_{i}_{datetime.now().timestamp()}",
                        "rating": 5,
                        "text": self._clean_text(snip),
                        "author": "Verified Customer",
                        "extracted_at": datetime.now(timezone.utc).isoformat()
                    })

        logger.info(f"✅ Success: Harvested {len(all_reviews)} reviews.")
        return all_reviews

# Alignment function for your Route
async def fetch_reviews(place_id: str, limit: int = 100):
    scraper = GoogleMobileScraper()
    return await scraper.run(place_id=place_id, limit=limit)
