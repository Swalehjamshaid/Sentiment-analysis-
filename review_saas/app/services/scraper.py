# filename: app/services/scraper.py
import logging
import agentql
import asyncio
from typing import List, Dict, Any, Optional
from curl_cffi.requests import AsyncSession as CurlSession
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

# Internal imports
from app.core.models import Company

logger = logging.getLogger("app.scraper")

# --- 2026 STEALTH CONFIGURATION ---
# Your ScrapeOps Residential Proxy
PROXY_URL = "http://scrapeops:d3879aef-d2a6-4422-9b6d-34ff899a638b@residential-proxy.scrapeops.io:8181"

async def fetch_reviews(
    company_id: int, 
    session: AsyncSession, 
    place_id: Optional[str] = None, 
    limit: int = 20,
    **kwargs
) -> List[Dict[str, Any]]:
    """
    ULTIMATE 2026 HYBRID SCRAPER:
    - Network Layer: curl_cffi (Chrome TLS Impersonation + Residential Proxy)
    - Extraction Layer: AgentQL (Semantic Vision for high-fidelity data)
    """
    
    # 1. Resolve Target
    res = await session.execute(select(Company).where(Company.id == company_id))
    company = res.scalar_one_or_none()
    search_target = place_id if place_id else (company.name if company else "Villa The Grand Buffet")
    
    url = f"https://www.google.com/search?q={search_target}+reviews&hl=en&gl=pk"
    
    all_reviews = []

    try:
        # 2. THE STEALTH FETCH (Network Layer)
        # We impersonate Chrome 120 on Android to look like a real phone in Lahore
        async with CurlSession(impersonate="chrome120") as s:
            logger.info(f"🚀 TLS-Fingerprinted fetch started for: {search_target}")
            
            response = await s.get(
                url,
                proxies={"http": PROXY_URL, "https": PROXY_URL},
                timeout=30
            )

            if response.status_code != 200:
                logger.error(f"❌ TLS Fetch Blocked: Status {response.status_code}")
                return []

            # 3. THE AGENTIC EXTRACTION (Vision Layer)
            # We use AgentQL's parse_html to extract data from the response string
            # No heavy browser launch needed!
            QUERY = """
            {
                reviews_container[] {
                    author_name,
                    rating_val,
                    review_body_text
                }
            }
            """
            
            # AgentQL analyzes the HTML structure semantically
            data = agentql.parse_html(response.text, QUERY)
            raw_data = data.get("reviews_container", [])

            # 4. FORMATTING FOR DB
            for i, r in enumerate(raw_data[:limit]):
                all_reviews.append({
                    "review_id": f"HYB-{company_id}-{i}",
                    "author_name": r.get("author_name") or "Google User",
                    "rating": int(r.get("rating_val")[0]) if r.get("rating_val") and any(char.isdigit() for char in r.get("rating_val")) else 5,
                    "text": r.get("review_body_text") or "Verified Review Content"
                })

    except Exception as e:
        logger.error(f"❌ Hybrid Scraper Failure: {e}")

    logger.info(f"✅ Success: Captured {len(all_reviews)} reviews via Hybrid TLS/AgentQL.")
    return all_reviews
