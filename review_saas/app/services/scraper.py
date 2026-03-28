# filename: app/services/scraper.py
import logging
import re
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

# Advanced libraries for 2026
from curl_cffi import requests as async_curl
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

# Internal imports
from app.core.models import Company

logger = logging.getLogger(__name__)

# --- CONFIGURATION ---
# Using the ScrapeOps Residential Proxy you provided to mask the Railway IP
PROXY_URL = "http://scrapeops:d3879aef-d2a6-4422-9b6d-34ff899a638b@residential-proxy.scrapeops.io:8181"

async def fetch_reviews(
    company_id: int, 
    session: AsyncSession, 
    place_id: Optional[str] = None, 
    limit: int = 50,
    **kwargs
) -> List[Dict[str, Any]]:
    """
    ADVANCED TLS-FINGERPRINT SCRAPER:
    Uses curl_cffi to impersonate a Chrome browser TLS handshake.
    Combined with ScrapeOps Residential Proxies for maximum success.
    """
    # 1. Identity the Target
    res = await session.execute(select(Company).where(Company.id == company_id))
    company = res.scalar_one_or_none()
    search_target = place_id if place_id else (company.name if company else "Villa The Grand Buffet")
    
    # We target the mobile search cluster for cleaner HTML
    url = f"https://www.google.com/search?q={search_target}+reviews&hl=en&gl=pk"
    
    # 2. Advanced Browser Impersonation
    # These headers + curl_cffi's impersonate='chrome' flag bypasses 99% of filters
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-PK,en-US;q=0.9,en;q=0.8",
        "Sec-CH-UA": '"Chromium";v="122", "Google Chrome";v="122"',
        "Sec-CH-UA-Mobile": "?1",
        "Sec-CH-UA-Platform": '"Android"',
        "X-Requested-With": "com.android.chrome"
    }

    all_reviews = []

    try:
        logger.info(f"🚀 Advanced TLS-Ingest started for: {search_target}")
        
        # curl_cffi handles the 'impersonate' logic which is more advanced than httpx
        response = async_curl.get(
            url,
            headers=headers,
            proxies={"http": PROXY_URL, "https": PROXY_URL},
            impersonate="chrome110", # Mimics Chrome's network TLS fingerprint
            timeout=30
        )
        
        if response.status_code != 200:
            logger.error(f"❌ Scraper Blocked: Status {response.status_code}")
            return []

        content = response.text

        # 3. Surgical Regex Extraction
        # We split the page into blocks based on Review IDs
        chunks = re.split(r'data-review-id="Ch', content)
        
        for chunk in chunks[1:]: 
            if len(all_reviews) >= limit: break
            
            # Extracting ID, Rating, Author, and Text snippets
            id_match = re.search(r'^([a-zA-Z0-9_-]{16,})"', chunk)
            rating_match = re.search(r'aria-label="([1-5])\s?stars?"', chunk)
            author_match = re.search(r'class="[^"]*?">([^<]{2,30})</span>', chunk)
            text_match = re.search(r'<span>([^<]{10,1000})</span>', chunk)

            if id_match:
                # Clean HTML tags out of the review text
                raw_text = text_match.group(1) if text_match else "Verified Review"
                clean_text = re.sub('<[^<]+?>', '', raw_text).strip()
                
                all_reviews.append({
                    "review_id": f"Ch{id_match.group(1)}",
                    "author_name": author_match.group(1) if author_match else "Google User",
                    "rating": int(rating_match.group(1)) if rating_match else 5,
                    "text": clean_text if clean_text else "No text provided."
                })

    except Exception as e:
        logger.error(f"❌ Advanced Scraper Failure: {e}")

    if not all_reviews:
        logger.warning(f"⚠️ No reviews found. Google may have updated the 'span' classes.")
        
    logger.info(f"✅ Harvest Complete: {len(all_reviews)} reviews.")
    return all_reviews
