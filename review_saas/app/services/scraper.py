import os
import logging
from typing import List, Dict, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from serpapi import GoogleSearch
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

logger = logging.getLogger("app.scraper")


async def fetch_reviews(
    place_id: Optional[str] = None,
    company_id: Optional[int] = None,
    limit: int = 300,
    name: Optional[str] = None,
    session: AsyncSession = None
) -> List[Dict]:
    """
    Fetch Google reviews using CID from company_cids table only.
    """
    analyzer = SentimentIntensityAnalyzer()
    
    api_key = os.getenv("SERP_API_KEY")
    if not api_key:
        logger.error("❌ SERP_API_KEY environment variable is not set!")
        return []

    cid = None
    target_name = (name or "Unknown Business").strip()

    # 1. Lookup CID from Database
    if company_id and session:
        try:
            from app.core.models import CompanyCID
            logger.info(f"📋 Looking up CID for company_id={company_id} | Name: {target_name}")

            result = await session.execute(
                select(CompanyCID).where(CompanyCID.company_id == company_id)
            )
            db_entry = result.scalar_one_or_none()

            if db_entry and db_entry.cid:
                cid = db_entry.cid
                logger.info(f"✅ CID successfully loaded from database: {cid}")
            else:
                logger.warning(f"⚠️ No CID found in company_cids table for company_id {company_id} ({target_name})")
                
        except Exception as e:
            logger.error(f"❌ Failed to read CompanyCID table: {e}")
    else:
        logger.error("❌ company_id or database session is missing.")

    # Early exit if no CID
    if not cid:
        logger.error(f"❌ No CID available in database for '{target_name}'. "
                    f"Please insert CID into company_cids table first.")
        return []

    # 2. Call SerpApi (only reached if CID exists)
    try:
        logger.info(f"📍 Calling SerpApi with CID: {cid} for {target_name}")

        params = {
            "engine": "google_maps_reviews",
            "data_id": cid,
            "api_key": api_key,
            "hl": "en",
            "no_cache": True,
            "num": min(limit, 100),
        }

        # Try newest reviews first
        params["sort_by"] = "newestFirst"
        search = GoogleSearch(params)
        results = search.get_dict()
        raw_reviews = results.get("reviews", [])

        metadata = results.get("search_metadata", {})
        logger.info(f"✅ SerpApi Response → Status: {metadata.get('status')} | "
                   f"Reviews Returned: {len(raw_reviews)}")

        if len(raw_reviews) == 0:
            logger.warning("⚠️ SerpApi returned 0 reviews. Trying fallback...")
            params["sort_by"] = "qualityScore"
            search = GoogleSearch(params)
            raw_reviews = search.get_dict().get("reviews", [])

        # Convert to final format
        final_results = []
        for r in raw_reviews[:limit]:
            body = r.get("snippet") or r.get("text") or r.get("content") or "No comment"
            vs = analyzer.polarity_scores(body)
            final_results.append({
                "review_id": r.get("review_id") or r.get("data_id"),
                "author_name": r.get("user", {}).get("name", "Anonymous"),
                "rating": r.get("rating", 0),
                "text": body,
                "sentiment": "Positive" if vs['compound'] >= 0.05 else "Negative",
            })

        logger.info(f"✅ Successfully captured {len(final_results)} reviews for '{target_name}'.")
        return final_results

    except Exception as e:
        logger.error(f"❌ SerpApi call failed for CID {cid}: {e}", exc_info=True)
        return []
