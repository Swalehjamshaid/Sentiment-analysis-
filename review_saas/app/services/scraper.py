# filename: app/services/scraper.py
import os
import logging
import asyncio
from urllib.parse import quote, quote_plus
from typing import List, Dict, Any, Optional

import agentql
from curl_cffi.requests import AsyncSession as CurlSession
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Internal imports
from app.core.models import Company, CompanyCID

logger = logging.getLogger("app.scraper")

# --- STEALTH CONFIGURATION ---
PROXY_URL = "http://scrapeops:d3879aef-d2a6-4422-9b6d-34ff899a638b@residential-proxy.scrapeops.io:8181"

async def fetch_reviews(
    company_id: int,
    session: AsyncSession,
    place_id: Optional[str] = None,
    limit: int = 30,
    **kwargs
) -> List[Dict[Any, Any]]:
    """
    ULTIMATE 2026 DODGER (V2):
    Fixes the 'curl (3) Malformed Input' by strictly encoding all URL paths.
    Ensures 'The Grand Buffet' becomes 'The%20Grand%20Buffet' so curl accepts it.
    """
    all_reviews = []
    target_name = "Unknown"

    try:
        # 1. Resolve Company Details
        res = await session.execute(select(Company).where(Company.id == company_id))
        company = res.scalar_one_or_none()

        if not company:
            logger.error(f"❌ Company ID {company_id} not found.")
            return []

        target_name = company.name
        logger.info(f"🚀 Starting review scrape for: {target_name} (ID: {company_id})")

        # 2. Get CID from database
        cid = None
        try:
            cid_res = await session.execute(
                select(CompanyCID).where(CompanyCID.company_id == company_id)
            )
            cid_entry = cid_res.scalar_one_or_none()
            if cid_entry and cid_entry.cid:
                cid = cid_entry.cid
                logger.info(f"✅ CID loaded: {cid}")
        except Exception as e:
            logger.warning(f"⚠️ CID table read skip: {e}")

        # 3. BUILD THE URL (With Strict Encoding)
        # We use quote() to handle spaces in IDs and quote_plus() for search queries
        if cid:
            search_url = f"https://www.google.com/maps?cid={quote(str(cid))}"
        elif place_id or company.google_place_id:
            pid = place_id or company.google_place_id
            search_url = f"https://www.google.com/maps/search/?api=1&query=Google&query_place_id={quote(str(pid))}"
        else:
            query_encoded = quote_plus(f"{target_name} reviews")
            search_url = f"https://www.google.com/search?q={query_encoded}&hl=en&gl=pk"
        
        logger.info(f"🔗 Target URL generated: {search_url}")

        # 4. STEALTH FETCH
        async with CurlSession(impersonate="chrome120") as s:
            logger.info("🛰️ Bypassing Google anti-bot via TLS fingerprinting...")
            
            response = await s.get(
                search_url,
                proxies={"http": PROXY_URL, "https": PROXY_URL},
                timeout=45,
                headers={
                    "Accept-Language": "en-US,en;q=0.9",
                    "Referer": "https://www.google.com/",
                    "Upgrade-Insecure-Requests": "1"
                }
            )

            if response.status_code != 200:
                logger.error(f"❌ Blocked by Google. Status: {response.status_code}")
                return []

            logger.info(f"✅ Page fetched ({len(response.text)} bytes)")

        # 5. AGENTQL EXTRACTION
        QUERY = """
        {
            reviews[] {
                author_name,
                rating_score,
                review_text,
                review_date
            }
        }
        """

        logger.info("🤖 AgentQL semantic parsing...")
        data = agentql.parse_html(response.text, QUERY)
        raw_reviews = data.get("reviews", []) or []

        # 6. MAPPING
        for i, r in enumerate(raw_reviews[:limit]):
            all_reviews.append({
                "review_id": f"DODGE-{company_id}-{i}",
                "author_name": r.get("author_name") or "Google User",
                "rating": 5, 
                "text": r.get("review_text") or "No text content.",
                "date": r.get("review_date")
            })

    except Exception as e:
        logger.error(f"❌ Scraper failure for {target_name}: {str(e)}", exc_info=True)

    logger.info(f"🏁 Finished: Captured {len(all_reviews)} reviews.")
    return all_reviews
