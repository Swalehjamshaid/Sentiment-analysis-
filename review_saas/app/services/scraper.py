# filename: app/services/scraper.py
from __future__ import annotations
import logging
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from serpapi import GoogleSearch

# Internal imports
from app.core.models import Company, CompanyCID

logger = logging.getLogger("app.scraper")

# Your SerpApi Key
SERPAPI_KEY = "f9f41e452ea716cale760081b94763a404c9ele07aef30def9c6a05391890e8d"

async def resolve_cid_via_serpapi(company_name: str, place_id: str) -> Optional[str]:
    """
    Improved Resolver: Tries Place ID first, then falls back to Name search.
    """
    try:
        # Try 1: Search by Place ID
        logger.info(f"🔍 SerpApi: Trying Place ID resolution for {company_name}")
        params = {
            "engine": "google_maps",
            "q": place_id,
            "api_key": SERPAPI_KEY
        }
        search = GoogleSearch(params)
        results = search.get_dict()
        cid = results.get("place_results", {}).get("data_id")

        # Try 2: Fallback to Name + Place ID if first try failed
        if not cid:
            logger.info(f"🔄 Fallback: Searching by Name '{company_name}'")
            params["q"] = company_name
            search = GoogleSearch(params)
            results = search.get_dict()
            
            # Check local results for a matching place_id
            local_results = results.get("local_results", [])
            for res in local_results:
                if res.get("place_id") == place_id or company_name.lower() in res.get("title", "").lower():
                    cid = res.get("data_id")
                    break
        
        return cid
    except Exception as e:
        logger.error(f"❌ SerpApi Resolution Error: {str(e)}")
        return None

async def fetch_reviews(
    company_id: int, 
    session: AsyncSession, 
    place_id: Optional[str] = None, 
    limit: int = 100,
    **kwargs
) -> List[Dict[str, Any]]:
    """
    Unified Scraper Logic:
    1. Checks DB for existing CID.
    2. If missing, resolves via API and SAVES it to the DB.
    3. Fetches reviews and returns them to the FastAPI route.
    """
    # Step A: Check for existing CID in database
    stmt = select(CompanyCID).where(CompanyCID.company_id == company_id)
    result = await session.execute(stmt)
    cid_record = result.scalar_one_or_none()
    
    target_cid = None
    if cid_record:
        target_cid = cid_record.cid
    elif place_id:
        # Get company name for better search fallback
        comp_stmt = select(Company).where(Company.id == company_id)
        comp_result = await session.execute(comp_stmt)
        company = comp_result.scalar_one_or_none()
        company_name = company.name if company else "Unknown"

        # Step B: Auto-Fix
        logger.warning(f"⚠️ CID missing for {company_name}. Attempting smart resolution...")
        target_cid = await resolve_cid_via_serpapi(company_name, place_id)
        
        if target_cid:
            new_cid = CompanyCID(
                company_id=company_id,
                cid=target_cid,
                place_id=place_id
            )
            session.add(new_cid)
            await session.commit() 
            logger.info(f"🔥 AUTO-FIX: Saved CID {target_cid} for {company_name}")

    if not target_cid:
        logger.error(f"❌ No CID available for Company {company_id}. Ingest failed.")
        return []

    # Step C: Fetch Reviews
    try:
        logger.info(f"🚀 Scraping reviews for CID: {target_cid}")
        params = {
            "engine": "google_maps_reviews",
            "data_id": target_cid,
            "api_key": SERPAPI_KEY,
            "num": limit
        }
        search = GoogleSearch(params)
        results = search.get_dict()
        
        raw_reviews = results.get("reviews", [])
        
        return [
            {
                "review_id": r.get("review_id"),
                "author_name": r.get("user", {}).get("name", "Anonymous"),
                "rating": r.get("rating", 0),
                "text": r.get("snippet", "")
            }
            for r in raw_reviews
        ]

    except Exception as e:
        logger.error(f"❌ Scraping Error: {str(e)}")
        return []
