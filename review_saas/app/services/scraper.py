import os
import logging
from datetime import datetime
from typing import List, Dict, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from serpapi import GoogleSearch
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

# Core project imports
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
    100% Complete Scraper:
    - Checks DB for CID to save API credits.
    - Resolves Place ID to CID via SerpApi.
    - Falls back to Name Search if ID resolution fails.
    """
    analyzer = SentimentIntensityAnalyzer()
    api_key = os.getenv("SERP_API_KEY", "f9f41e452ea716cale760081b94763a404c9ele07aef30def9c6a05391890e8d")
    cid = None
    target_name = name or "Restaurant Lahore"

    # 1. DATABASE CID CHECK
    if company_id and session:
        try:
            # Inline import prevents 'ImportError' if table is being created
            from app.core.models import CompanyCID
            result = await session.execute(
                select(CompanyCID).where(CompanyCID.company_id == company_id)
            )
            db_entry = result.scalar_one_or_none()
            if db_entry:
                cid = db_entry.cid
                logger.info(f"✅ Using cached CID from Database: {cid}")
        except Exception:
            logger.info("ℹ️ CompanyCID table not detected. Proceeding to API resolution.")

    # 2. RESOLVE CID VIA SERPAPI
    if not cid:
        try:
            # Attempt 1: Resolve using Google Place ID (ChIJ...)
            if place_id:
                search = GoogleSearch({
                    "engine": "google_maps",
                    "place_id": place_id,
                    "api_key": api_key,
                    "no_cache": True
                })
                cid = search.get_dict().get("place_results", {}).get("data_id")

            # Attempt 2: Resolve using Company Name (e.g. Salt'n Pepper)
            if not cid:
                logger.warning(f"⚠️ ID Resolution failed. Searching by Name: {target_name}")
                search_fb = GoogleSearch({
                    "engine": "google_maps",
                    "q": target_name,
                    "api_key": api_key
                })
                fb_res = search_fb.get_dict()
                local = fb_res.get("local_results", [])
                place_fb = fb_res.get("place_results") or (local[0] if local else {})
                cid = place_fb.get("data_id")

            # SAVE RESOLVED CID TO DB
            if cid and company_id and session:
                try:
                    from app.core.models import CompanyCID
                    new_cid_entry = CompanyCID(company_id=company_id, cid=cid)
                    session.add(new_cid_entry)
                    # We commit here so the CID is saved even if review-fetching fails later
                    await session.commit()
                except:
                    await session.rollback()

        except Exception as e:
            logger.error(f"❌ CID Resolution Error: {e}")

    if not cid:
        logger.error(f"❌ Failed to resolve a valid CID for {target_name}")
        return []

    # 3. FETCH REVIEWS
    try:
        logging.info(f"📍 CID Resolved: {cid}. Pulling {limit} reviews...")
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
