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
) -> List[Dict[str, Optional[str]]]:
    """
    Clean version: Only fetches CID from PostgreSQL database.
    No hardcoded bypass logic.
    """
    analyzer = SentimentIntensityAnalyzer()
    
    # Get API key from environment
    api_key = os.getenv("SERP_API_KEY")
    if not api_key:
        logger.error("❌ SERP_API_KEY environment variable is missing!")
        return []

    cid = None
    target_name = (name or "Business").upper()

    # ==================== ONLY DATABASE LOOKUP ====================
    if company_id and session:
        try:
            from app.core.models import CompanyCID
            
            logger.info(f"📋 Looking up CID from database for company_id: {company_id}")
            
            result = await session.execute(
                select(CompanyCID).where(CompanyCID.company_id == company_id)
            )
            db_entry = result.scalar_one_or_none()
            
            if db_entry and db_entry.cid:
                cid = db_entry.cid
                logger.info(f"✅ CID successfully loaded from database: {cid}")
            else:
                logger.warning(f"⚠️ No CID found in database for company_id: {company_id} (Name: {target_name})")
                
        except Exception as e:
            logger.error(f"❌ Database lookup failed: {e}", exc_info=True)
    else:
        logger.error("❌ Cannot fetch reviews: company_id or database session is missing.")

    # If no CID found in DB, abort
    if not cid:
        logger.error(f"❌ No CID available in database for {target_name}. Cannot fetch reviews.")
        return []

    # ==================== FETCH REVIEWS USING CID FROM DB ====================
    try:
        logger.info(f"📍 Fetching reviews for CID (from DB): {cid} | Limit: {limit}")

        params = {
            "engine": "google_maps_reviews",
            "data_id": cid,
            "api_key": api_key,
            "hl": "en",
            "no_cache": True,
        }

        # First attempt - Newest reviews
        search_params = params.copy()
        search_params.update({
            "sort_by": "newestFirst",
            "num": min(limit, 100)
        })

        search_reviews = GoogleSearch(search_params)
        results = search_reviews.get_dict()

        raw_reviews = results.get("reviews", [])

        # Logging for debugging
        metadata = results.get("search_metadata", {})
        logger.info(f"SerpApi status: {metadata.get('status')} | "
                   f"Reviews returned: {len(raw_reviews)}")

        # Fallback attempt if zero reviews
        if len(raw_reviews) == 0:
            logger.warning(f"⚠️ Zero reviews returned. Trying fallback parameters...")

            search_params = params.copy()
            search_params.update({
                "sort_by": "qualityScore",
                "num": 50
            })

            search_reviews = GoogleSearch(search_params)
            results = search_reviews.get_dict()
            raw_reviews = results.get("reviews", [])

            logger.info(f"Fallback attempt returned {len(raw_reviews)} reviews.")

        # Process the reviews
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

        logger.info(f"✅ Success: Captured {len(final_results)} reviews from database CID.")
        return final_results

    except Exception as e:
        logger.error(f"❌ Review fetch failed for CID {cid}: {e}", exc_info=True)
        return []
