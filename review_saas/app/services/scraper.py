# filename: app/services/scraper.py
import httpx
import logging
import re
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.models import Company

logger = logging.getLogger(__name__)

async def fetch_reviews(
    company_id: int, 
    session: AsyncSession, 
    place_id: Optional[str] = None, 
    limit: int = 50,
    **kwargs
) -> List[Dict[str, Any]]:
    """
    UPGRADED MUS SCRAPER:
    Uses multi-step parsing to prevent 'Local Reviewer' fallbacks.
    """
    res = await session.execute(select(Company).where(Company.id == company_id))
    company = res.scalar_one_or_none()
    search_target = place_id if place_id else (company.name if company else "Villa The Grand Buffet")
    
    # We use a broader search URL to ensure we get the mobile review overlay
    url = f"https://www.google.com/search?q={search_target}+reviews&hl=en&gl=pk"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.6261.105 Mobile Safari/537.36",
        "X-Requested-With": "com.android.chrome",
        "Sec-CH-UA-Platform": '"Android"'
    }

    all_reviews = []

    async with httpx.AsyncClient(headers=headers, timeout=30.0, follow_redirects=True) as client:
        try:
            response = await client.get(url)
            content = response.text

            # 1. Split content into individual review chunks first
            # This prevents one bad review from breaking the whole list
            chunks = re.split(r'data-review-id="Ch', content)
            
            for chunk in chunks[1:]: # Skip the first chunk before the first ID
                if len(all_reviews) >= limit: break
                
                # Extract ID
                id_match = re.search(r'^([a-zA-Z0-9_-]{16,})"', chunk)
                # Extract Rating (Looking for the digit before "stars")
                rating_match = re.search(r'aria-label="([1-5])\s?stars?"', chunk)
                # Extract Author (Looking for common mobile name patterns)
                author_match = re.search(r'class="[^"]*?">([^<]{2,30})</span>', chunk)
                # Extract Text (Looking for the main review body)
                text_match = re.search(r'<span>([^<]{5,500})</span>', chunk)

                if id_match:
                    all_reviews.append({
                        "review_id": f"Ch{id_match.group(1)}",
                        "author_name": author_match.group(1) if author_match else "Google User",
                        "rating": int(rating_match.group(1)) if rating_match else 5,
                        "text": re.sub('<[^<]+?>', '', text_match.group(1)).strip() if text_match else "No text provided."
                    })

        except Exception as e:
            logger.error(f"❌ MUS Error: {e}")

    # Final Guard: Only use hardcoded fallback if absolutely NO data was found
    if not all_reviews:
        logger.warning("⚠️ Scraper totally blocked. Check Railway IP status.")
        
    return all_reviews
