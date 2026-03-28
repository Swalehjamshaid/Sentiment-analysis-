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
    Fetch Google reviews using CID from company_cids table.
    Improved logging and fallback using google_place_id if CID is missing.
    """
    analyzer = SentimentIntensityAnalyzer()
    
    api_key = os.getenv("SERP_API_KEY")
    if not api_key:
        logger.error("❌ SERP_API_KEY environment variable is not set!")
        return []

    cid = None
    target_name = (name or "Unknown Business").strip()

    # ==================== 1. Try to get CID from Database ====================
    if company_id and session:
        try:
            from app.core.models import CompanyCID, Company
            
            logger.info(f"📋 Looking up CID for company_id={company_id} | Name: {target_name}")

            # Primary lookup: CompanyCID table
            result = await session.execute(
                select(CompanyCID).where(CompanyCID.company_id == company_id)
            )
            db_entry = result.scalar_one_or_none()

            if db_entry and db_entry.cid:
                cid = db_entry.cid
                logger.info(f"✅ CID loaded from company_cids table: {cid}")
            else:
                logger.warning(f"⚠️ No CID found in company_cids for company_id {company_id}")

                # Fallback: Try to get google_place_id from Company table and resolve CID
                if place_id:
                    logger.info(f"🔄 No CID found. Trying to resolve using google_place_id: {place_id}")
                    try:
                        search = GoogleSearch({
                            "engine": "google_maps",
                            "place_id": place_id,
                            "api_key": api_key,
                            "hl": "en"
                        })
                        resolved_cid = search.get_dict().get("place_results", {}).get("data_id")
                        if resolved_cid:
                            cid = resolved_cid
                            logger.info(f"✅ CID resolved using google_place_id: {cid}")
                    except Exception as e:
                        logger.warning(f"Failed to resolve CID from place_id: {e}")

        except Exception as e:
            logger.error(f"❌ Error accessing CompanyCID or Company table: {e}")

    if not cid:
        logger.error(f"❌ No CID available for '{target_name}' (company_id={company_id}). "
                    f"Please insert correct CID into company_cids table.")
        return []

    # ==================== 2. Fetch Reviews using CID ====================
    try:
        logger.info(f"📍 Fetching reviews from SerpApi using CID: {cid}")

        params = {
            "engine": "google_maps_reviews",
            "data_id": cid,
            "api_key": api_key,
            "hl": "en",
            "no_cache": True,
            "num": min(limit, 100),
        }

        # First attempt - newest reviews
        params["sort_by"] = "newestFirst"
        search_reviews = GoogleSearch(params)
        results = search_reviews.get_dict()
        raw_reviews = results.get("reviews", [])

        metadata = results.get("search_metadata", {})
        logger.info(f"✅ SerpApi Response | Status: {metadata.get('status')} | "
                   f"Reviews Returned: {len(raw_reviews)}")

        # Fallback if zero reviews
        if len(raw_reviews) == 0:
            logger.warning("⚠️ No reviews returned. Trying fallback sort...")
            params["sort_by"] = "qualityScore"
            search_reviews = GoogleSearch(params)
            raw_reviews = search_reviews.get_dict().get("reviews", [])
            logger.info(f"Fallback returned {len(raw_reviews)} reviews.")

        # Process reviews
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
        logger.error(f"❌ SerpApi failed for CID {cid}: {e}", exc_info=True)
        return []
