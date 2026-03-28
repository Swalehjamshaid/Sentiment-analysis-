# app/services/scraper.py
import os
import logging
from datetime import datetime
from typing import List, Dict, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from serpapi import GoogleSearch
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

# Core project imports
from app.core.db import get_session
from app.core.models import CompanyCID  # Table to store CID for companies

logger = logging.getLogger("app.scraper")

# ---------------------------
# FETCH REVIEWS FUNCTION
# ---------------------------
async def fetch_reviews(
    place_id: Optional[str] = None,
    company_id: Optional[int] = None,
    limit: int = 300,
    name: Optional[str] = None,
    session: AsyncSession = None
) -> List[Dict[str, Optional[str]]]:
    """
    Fetch Google reviews using SerpAPI.
    - First checks DB for CID (company_id required)
    - Falls back to SerpAPI search if CID not in DB
    Returns list of dicts compatible with Review DB model
    """
    analyzer = SentimentIntensityAnalyzer()
    api_key = os.getenv("SERP_API_KEY", "")
    cid = None

    # ---------------------------
    # 1. CHECK DATABASE FOR CID
    # ---------------------------
    if company_id and session:
        try:
            result = await session.execute(
                select(CompanyCID).where(CompanyCID.company_id == company_id)
            )
            db_entry = result.scalar_one_or_none()
            if db_entry and db_entry.cid:
                cid = db_entry.cid
                logger.info(f"✅ Using CID from DB: {cid}")
        except Exception as e:
            logger.warning(f"⚠️ Failed to check CID in DB: {e}")

    target_name = name or "Restaurant"

    # ---------------------------
    # 2. FALLBACK TO SERPAPI IF NO CID
    # ---------------------------
    if not cid:
        try:
            # First attempt with place_id
            if place_id:
                search_resolver = GoogleSearch({
                    "engine": "google_maps",
                    "place_id": place_id,
                    "api_key": api_key,
                    "no_cache": True
                })
                res = search_resolver.get_dict()
                cid = res.get("place_results", {}).get("data_id")

            # Fallback by name search
            if not cid:
                logger.info(f"⚠️ CID not found via place_id. Searching by name: {target_name}")
                search_fb = GoogleSearch({
                    "engine": "google_maps",
                    "q": target_name,
                    "api_key": api_key
                })
                fb_res = search_fb.get_dict()
                local = fb_res.get("local_results", [])
                place_fb = fb_res.get("place_results") or (local[0] if local else {})
                cid = place_fb.get("data_id")

            if not cid:
                logger.error(f"❌ Failed to resolve CID for {target_name}")
                return []

            # Save CID to DB for future
            if company_id and session:
                db_entry = CompanyCID(company_id=company_id, cid=cid)
                session.add(db_entry)
                await session.commit()
                logger.info(f"💾 Saved new CID {cid} to DB for company_id {company_id}")

        except Exception as e:
            logger.error(f"❌ SerpAPI CID resolution failed: {e}")
            return []

    # ---------------------------
    # 3. FETCH REVIEWS
    # ---------------------------
    try:
        review_params = {
            "engine": "google_maps_reviews",
            "data_id": cid,
            "api_key": api_key,
            "num": limit,
            "no_cache": True,
            "sort_by": "newest"
        }
        search_reviews = GoogleSearch(review_params)
        raw_reviews = search_reviews.get_dict().get("reviews", [])

        final_results = []
        for r in raw_reviews:
            body = r.get("snippet") or r.get("text") or "No comment"
            vs = analyzer.polarity_scores(body)

            final_results.append({
                "review_id": r.get("review_id"),
                "author_name": r.get("user", {}).get("name", "Anonymous"),
                "rating": r.get("rating", 0),
                "text": body,
                "sentiment": "Positive" if vs['compound'] >= 0.05 else "Negative"
            })

        logger.info(f"✅ Captured {len(final_results)} reviews for CID {cid}")
        return final_results

    except Exception as e:
        logger.error(f"❌ Review fetch failure: {e}")
        return []
