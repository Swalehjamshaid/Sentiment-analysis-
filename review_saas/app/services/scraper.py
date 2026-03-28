import os
import logging
from datetime import datetime
from typing import List, Dict, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from serpapi import GoogleSearch
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

# Core project imports - Do NOT import CompanyCID here to avoid boot-time crashes
from app.core.db import engine

logger = logging.getLogger("app.scraper")

async def fetch_reviews(
    place_id: Optional[str] = None,
    company_id: Optional[int] = None,
    limit: int = 300,
    name: Optional[str] = None,
    session: AsyncSession = None
) -> List[Dict[str, Optional[str]]]:
    """
    ULTIMATE SCRAPER:
    - Resolves Google Place ID (ChIJ) to CID (Data ID).
    - Precision fallback for Miami/Lahore locations.
    - Safe-import logic to prevent Railway Worker Boot Errors.
    """
    analyzer = SentimentIntensityAnalyzer()
    api_key = os.getenv("SERP_API_KEY", "f9f41e452ea716cale760081b94763a404c9ele07aef30def9c6a05391890e8d")
    cid = None
    target_name = name or "Business"

    # --- 1. DATABASE CID CACHE CHECK ---
    if company_id and session:
        try:
            # Inline import prevents the 'ImportError' during Gunicorn boot
            from app.core.models import CompanyCID
            result = await session.execute(
                select(CompanyCID).where(CompanyCID.company_id == company_id)
            )
            db_entry = result.scalar_one_or_none()
            if db_entry:
                cid = db_entry.cid
                logger.info(f"✅ Using cached CID from DB: {cid}")
        except Exception:
            # If the table doesn't exist yet, we just skip the cache and hit the API
            logger.info("ℹ️ CompanyCID table not detected. Resolving via SerpApi.")

    # --- 2. SERPAPI RESOLUTION (Place ID -> CID) ---
    if not cid:
        try:
            # Attempt A: Direct Place ID resolution (Using the ID from your DB screenshot)
            if place_id:
                search = GoogleSearch({
                    "engine": "google_maps",
                    "place_id": place_id,
                    "api_key": api_key,
                    "no_cache": True
                })
                cid = search.get_dict().get("place_results", {}).get("data_id")

            # Attempt B: Precision Name + "Reviews" search (Fixes E11EVEN MIAMI resolution)
            if not cid:
                logger.warning(f"⚠️ ID Resolution failed for {place_id}. Trying Precision Search: {target_name}")
                search_fb = GoogleSearch({
                    "engine": "google_maps",
                    "q": f"{target_name} reviews", 
                    "api_key": api_key
                })
                fb_res = search_fb.get_dict()
                
                # Check local results (common for venues and restaurants in Lahore/Miami)
                local = fb_res.get("local_results", [])
                place_fb = fb_res.get("place_results") or (local[0] if local else {})
                cid = place_fb.get("data_id")

            # --- 3. CACHE THE RESOLVED CID ---
            if cid and company_id and session:
                try:
                    from app.core.models import CompanyCID
                    new_cache = CompanyCID(company_id=company_id, cid=cid)
                    session.add(new_cache)
                    await session.commit()
                    logger.info(f"💾 CID {cid} cached for {target_name}")
                except Exception as db_err:
                    await session.rollback()
                    logger.warning(f"⚠️ Could not cache CID: {db_err}")

        except Exception as e:
            logger.error(f"❌ Resolution Critical Failure: {e}")

    if not cid:
        logger.error(f"❌ Failed to resolve CID for {target_name}. Search query was too broad.")
        return []

    # --- 4. FETCH ACTUAL REVIEWS ---
    try:
        logging.info(f"📍 CID Resolved: {cid}. Pulling up to {limit} reviews...")
        search_reviews = GoogleSearch({
            "engine": "google_maps_reviews",
            "data_id": cid,
            "api_key": api_key,
            "num": limit,
            "no_cache": True,
            "sort_by": "newest"
        })
        raw_reviews = search_reviews.get_dict().get("reviews", [])
        
        final_results = []
        for r in raw_reviews:
            body = r.get("snippet") or r.get("text") or "No comment provided"
            vs = analyzer.polarity_scores(body)
            final_results.append({
                "review_id": r.get("review_id"),
                "author_name": r.get("user", {}).get("name", "Anonymous"),
                "rating": r.get("rating", 0),
                "text": body,
                "sentiment": "Positive" if vs['compound'] >= 0.05 else "Negative"
            })
        
        logger.info(f"✅ Success: Captured {len(final_results)} reviews.")
        return final_results

    except Exception as e:
        logger.error(f"❌ Review Fetch Failure: {e}")
        return []
