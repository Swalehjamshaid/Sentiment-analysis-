import os
import logging
from typing import List, Dict, Optional
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
    Fetches reviews using CID from PostgreSQL database only.
    No hardcoded bypass.
    """
    analyzer = SentimentIntensityAnalyzer()
    
    api_key = os.getenv("SERP_API_KEY")
    if not api_key:
        logger.error("❌ SERP_API_KEY environment variable is missing!")
        return []

    cid = None
    target_name = (name or "Business").upper()

    # ==================== SAFE DATABASE LOOKUP ====================
    if company_id and session:
        try:
            # Import inside try block to prevent crash if model doesn't exist
            from app.core.models import CompanyCID
            
            logger.info(f"📋 Looking up CID in database for company_id: {company_id} ({target_name})")
            
            result = await session.execute(
                select(CompanyCID).where(CompanyCID.company_id == company_id)
            )
            db_entry = result.scalar_one_or_none()
            
            if db_entry and db_entry.cid:
                cid = db_entry.cid
                logger.info(f"✅ CID loaded from database: {cid}")
            else:
                logger.warning(f"⚠️ No CID found in CompanyCID table for company_id {company_id}")
                
        except ImportError:
            logger.error("❌ Model 'CompanyCID' not found in app.core.models")
        except Exception as e:
            logger.error(f"❌ Database lookup error: {e}", exc_info=False)
    else:
        logger.error("❌ Missing company_id or database session")

    if not cid:
        logger.error(f"❌ No CID available in database for {target_name}. Cannot proceed.")
        return []

    # ==================== FETCH REVIEWS ====================
    try:
        logger.info(f"📍 Fetching reviews using CID from DB: {cid}")

        params = {
            "engine": "google_maps_reviews",
            "data_id": cid,
            "api_key": api_key,
            "hl": "en",
            "no_cache": True,
        }

        # Primary attempt
        search_params = params.copy()
        search_params.update({
            "sort_by": "newestFirst",
            "num": min(limit, 100)
        })

        search_reviews = GoogleSearch(search_params)
        results = search_reviews.get_dict()
        raw_reviews = results.get("reviews", [])

        metadata = results.get("search_metadata", {})
        logger.info(f"SerpApi status: {metadata.get('status')} | Reviews returned: {len(raw_reviews)}")

        # Fallback if zero reviews
        if len(raw_reviews) == 0:
            logger.warning("⚠️ No reviews from first attempt. Trying fallback...")
            search_params = params.copy()
            search_params.update({
                "sort_by": "qualityScore",
                "num": 50
            })
            search_reviews = GoogleSearch(search_params)
            raw_reviews = search_reviews.get_dict().get("reviews", [])
            logger.info(f"Fallback returned {len(raw_reviews)} reviews.")

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
                "date": r.get("date") or r.get("published_date"),
            })

        logger.info(f"✅ Successfully captured {len(final_results)} reviews.")
        return final_results

    except Exception as e:
        logger.error(f"❌ Failed to fetch reviews for CID {cid}: {e}", exc_info=True)
        return []
