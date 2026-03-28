# filename: app/services/scraper.py
from __future__ import annotations
import logging
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from serpapi import GoogleSearch

# Internal imports
from app.core.models import CompanyCID

# --- 1. SETUP LOGGING ---
logger = logging.getLogger("app.scraper")

# --- 2. CONFIGURATION ---
# Your SerpApi Key
SERPAPI_KEY = "f9f41e452ea716cale760081b94763a404c9ele07aef30def9c6a05391890e8d"

# --- 3. CID RESOLUTION (The "Fixer") ---

async def resolve_cid_via_serpapi(place_id: str) -> Optional[str]:
    """
    Calls SerpApi to find the unique CID (data_id) using a Google Place ID.
    Used if the database doesn't have the CID yet.
    """
    try:
        logger.info(f"🔍 Searching SerpApi for Place ID: {place_id}")
        params = {
            "engine": "google_maps",
            "q": place_id,
            "api_key": SERPAPI_KEY
        }
        # SerpApi library is synchronous, we call it directly
        search = GoogleSearch(params)
        results = search.get_dict()

        # Extract CID from 'place_results'
        cid = results.get("place_results", {}).get("data_id")

        # Fallback: Check 'local_results' if place_results is empty
        if not cid:
            local_results = results.get("local_results", [])
            if local_results:
                cid = local_results[0].get("data_id")
        
        return cid
    except Exception as e:
        logger.error(f"❌ SerpApi API Error during resolution: {str(e)}")
        return None

# --- 4. MAIN SCRAPER FUNCTION (fetch_reviews) ---
# This name MUST match the import in app/routes/reviews.py

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
        logger.info(f"✅ Found CID in DB for Company {company_id}: {target_cid}")
    elif place_id:
        # Step B: Auto-Fix (Resolve and Save)
        logger.warning(f"⚠️ CID missing for Company {company_id}. Resolving...")
        target_cid = await resolve_cid_via_serpapi(place_id)
        
        if target_cid:
            new_cid = CompanyCID(
                company_id=company_id,
                cid=target_cid,
                place_id=place_id
            )
            session.add(new_cid)
            await session.commit() # Save permanently to DB
            logger.info(f"🔥 AUTO-FIX: Saved CID {target_cid} to database.")

    if not target_cid:
        logger.error(f"❌ No CID available for Company {company_id}. Aborting.")
        return []

    # Step C: Fetch Reviews using SerpApi
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
        
        # Step D: Format exactly how app/routes/reviews.py expects it
        formatted_reviews = []
        for r in raw_reviews:
            formatted_reviews.append({
                "review_id": r.get("review_id"),
                "author_name": r.get("user", {}).get("name", "Anonymous"),
                "rating": r.get("rating", 0),
                "text": r.get("snippet", "")
            })
            
        return formatted_reviews

    except Exception as e:
        logger.error(f"❌ Scraping Error: {str(e)}")
        return []
