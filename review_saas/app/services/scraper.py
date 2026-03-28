import os
import logging
import asyncio
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
) -> List[Dict[str, Any]]:
    """
    Hybrid Scraper: First tries CID from company_cids table,
    falls back to google_place_id, then uses stealth + AgentQL.
    """
    all_reviews = []
    target_name = "Unknown"

    try:
        # 1. Get Company details
        res = await session.execute(select(Company).where(Company.id == company_id))
        company = res.scalar_one_or_none()

        if not company:
            logger.error(f"❌ Company with id {company_id} not found.")
            return []

        target_name = company.name
        logger.info(f"🚀 Starting review scrape for: {target_name} (ID: {company_id})")

        # 2. Get CID from database (Priority)
        cid = None
        try:
            cid_res = await session.execute(
                select(CompanyCID).where(CompanyCID.company_id == company_id)
            )
            cid_entry = cid_res.scalar_one_or_none()
            if cid_entry and cid_entry.cid:
                cid = cid_entry.cid
                logger.info(f"✅ CID loaded from database: {cid}")
        except Exception as e:
            logger.warning(f"⚠️ Could not read CompanyCID table: {e}")

        # 3. Build search URL
        if cid:
            # Better to use direct Maps URL with CID when available
            search_url = f"https://www.google.com/maps/place/?q=place_id:{cid}&hl=en"
            logger.info(f"Using CID-based URL: {search_url}")
        elif place_id or company.google_place_id:
            pid = place_id or company.google_place_id
            search_url = f"https://www.google.com/maps/place/?q=place_id:{pid}&hl=en"
            logger.info(f"Using google_place_id: {pid}")
        else:
            # Fallback to search
            search_url = f"https://www.google.com/search?q={target_name}+reviews&hl=en&gl=pk"
            logger.info(f"Using keyword search: {target_name} reviews")

        # 4. Stealth HTTP Request with ScrapeOps Proxy
        async with CurlSession(impersonate="chrome120") as s:
            logger.info(f"🛰️ Fetching page with TLS fingerprint via ScrapeOps proxy...")

            response = await s.get(
                search_url,
                proxies={"http": PROXY_URL, "https": PROXY_URL},
                timeout=45,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept-Language": "en-US,en;q=0.9",
                }
            )

            if response.status_code != 200:
                logger.error(f"❌ Request blocked or failed. Status: {response.status_code}")
                return []

            logger.info(f"✅ Page fetched successfully ({len(response.text)} bytes)")

        # 5. AgentQL Extraction - Improved Query
        QUERY = """
        {
            reviews[] {
                author_name,
                rating,
                review_text,
                review_date,
                likes_count
            }
        }
        """

        logger.info("🤖 Parsing page with AgentQL...")
        data = agentql.parse_html(response.text, QUERY)

        raw_reviews = data.get("reviews", []) or []

        # 6. Format output to match your Review model
        for i, r in enumerate(raw_reviews[:limit]):
            all_reviews.append({
                "review_id": f"AGQL-{company_id}-{i}",
                "author_name": r.get("author_name") or "Google User",
                "rating": int(r.get("rating") or 5),
                "text": r.get("review_text") or r.get("review_body_text") or "No review text available",
                "date": r.get("review_date"),
                "likes": r.get("likes_count", 0)
            })

        logger.info(f"✅ AgentQL extracted {len(all_reviews)} reviews.")

    except Exception as e:
        logger.error(f"❌ Scraper failed for company {company_id} ({target_name}): {str(e)}", exc_info=True)

    logger.info(f"🏁 Scraper finished for {target_name}: Captured {len(all_reviews)} reviews.")
    return all_reviews
