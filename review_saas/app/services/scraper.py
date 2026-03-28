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
    Fetch Google reviews using CID from the company_cids table only.
    No hardcoded bypass logic.
    """
    analyzer = SentimentIntensityAnalyzer()
    
    # Get SerpApi key from environment
    api_key = os.getenv("SERP_API_KEY")
    if not api_key:
        logger.error("❌ SERP_API_KEY environment variable is not set!")
        return []

    cid = None
    target_name = (name or "Unknown Business").strip()

    # ==================== 1. Get CID from Database ====================
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

    if not cid:
        logger.error(f"❌ No CID available in database for '{target_name}'. Cannot fetch reviews.")
        return []

    # ==================== 2. Fetch Reviews from SerpApi ====================
    try:
        logger.info(f"📍 Calling SerpApi for CID: {cid} | Limit: {limit}")

        params = {
            "engine": "google_maps_reviews",
            "data_id": cid,
            "api_key": api_key,
            "hl": "en",
            "no_cache": True,
        }

        # First attempt: Newest reviews
        search_params = params.copy()
        search_params.update({
            "sort_by": "newestFirst",
            "num": min(limit, 100)
        })

        search_reviews = GoogleSearch(search_params)
        results = search_reviews.get_dict()
        raw_reviews = results.get("reviews", [])

        # Detailed logging
        metadata = results.get("search_metadata", {})
        logger.info(f"SerpApi Status: {metadata.get('status')} | "
                   f"Reviews Returned: {len(raw_reviews)} | "
                   f"Time Taken: {metadata.get('time_taken')}s")

        # Fallback if no reviews
        if len(raw_reviews) == 0:
            logger.warning(f"⚠️ SerpApi returned 0 reviews. Trying fallback (most relevant)...")
            search_params = params.copy()
            search_params.update({
                "sort_by": "qualityScore",
                "num": 50
            })
            search_reviews = GoogleSearch(search_params)
            raw_reviews = search_reviews.get_dict().get("reviews", [])
            logger.info(f"Fallback attempt returned {len(raw_reviews)} reviews.")

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
                "date": r.get("date") or r.get("published_date"),
            })

        logger.info(f"✅ Successfully captured {len(final_results)} reviews for '{target_name}'.")
        return final_results

    except Exception as e:
        logger.error(f"❌ SerpApi request failed for CID {cid}: {str(e)}", exc_info=True)
        return []
