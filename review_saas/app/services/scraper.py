import os
import logging
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import re

from serpapi import GoogleSearch
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Company

logger = logging.getLogger("app.scraper")

# Using Railway environment variable with hardcoded fallback
SERPAPI_KEY = os.getenv("SERP_API_KEY", "f9f41e452ea716ca1e760081b94763a404c9e1e07aef30def9c6a05391890e8d")

def parse_relative_date(date_text: str) -> datetime:
    """
    Converts strings like '2 months ago' or 'a week ago' into a Python datetime object.
    """
    if not date_text or not isinstance(date_text, str):
        return datetime.utcnow()
    
    now = datetime.utcnow()
    # Extract the number from the string
    match = re.search(r'(\d+)', date_text)
    quantity = int(match.group(1)) if match else 1
    
    date_text = date_text.lower()
    
    if 'second' in date_text:
        return now - timedelta(seconds=quantity)
    elif 'minute' in date_text:
        return now - timedelta(minutes=quantity)
    elif 'hour' in date_text:
        return now - timedelta(hours=quantity)
    elif 'day' in date_text:
        return now - timedelta(days=quantity)
    elif 'week' in date_text:
        return now - timedelta(weeks=quantity)
    elif 'month' in date_text:
        return now - timedelta(days=quantity * 30)
    elif 'year' in date_text:
        return now - timedelta(days=quantity * 365)
    
    return now

async def fetch_reviews_from_google(
    place_id: Optional[str] = None,
    company_id: Optional[int] = None,
    session: Optional[AsyncSession] = None,
    target_limit: int = 500, # Minimum target set to 500
    **kwargs
) -> List[Dict[str, Any]]:
    all_reviews: List[Dict[str, Any]] = []

    try:
        target_place_id = place_id
        
        # Attribute: ID Discovery from DB
        if not target_place_id and company_id and session:
            result = await session.execute(select(Company).where(Company.id == company_id))
            company = result.scalar_one_or_none()
            target_place_id = company.google_place_id if company else None

        # Attribute: ID Discovery via Search fallback
        if not target_place_id or not target_place_id.startswith("ChIJ"):
            query = target_place_id or "Villa The Grand Buffet"
            search_params = {"engine": "google", "q": query, "api_key": SERPAPI_KEY, "gl": "pk"}
            def discover_id():
                res = GoogleSearch(search_params).get_dict()
                return res.get("local_results", [{}])[0].get("place_id") or res.get("knowledge_graph", {}).get("place_id")
            target_place_id = await asyncio.to_thread(discover_id)

        if not target_place_id:
            return []

        next_page_token: Optional[str] = None

        # CONTINUOUS FETCH LOGIC:
        # Loops until it hits the minimum (500) OR until Google has no more reviews left.
        while True:
            params = {
                "engine": "google_maps_reviews",
                "place_id": target_place_id,
                "api_key": SERPAPI_KEY,
                "next_page_token": next_page_token,
                "sort_by": "newest" # Attribute: Ensures fetching based on date range (newest first)
            }

            results = await asyncio.to_thread(lambda: GoogleSearch(params).get_dict())
            reviews = results.get("reviews", [])

            if not reviews:
                break

            for r in reviews:
                # Attribute: Date range parsing
                raw_date = r.get("date", "")
                parsed_date = parse_relative_date(raw_date)

                # Attribute: Original Output Mapping
                all_reviews.append({
                    "google_review_id": r.get("review_id"),
                    "author_name": r.get("user", {}).get("name"),
                    "rating": int(r.get("rating", 5)),
                    "text": r.get("text") or r.get("snippet") or "No content",
                    "google_review_time": parsed_date, 
                    "review_likes": r.get("likes", 0)
                })

            # Check for next page
            next_page_token = results.get("serpapi_pagination", {}).get("next_page_token")
            
            # If we have reached 500 and there is no specific date-range stop logic in kwargs,
            # we can continue or stop based on the availability of data.
            if not next_page_token:
                break
                
            # If you want it to be truly "no limit", we only break when next_page_token is gone.
            # We only keep the 500 as a 'minimum' check.
            if len(all_reviews) >= target_limit and not next_page_token:
                break

    except Exception as exc:
        logger.error(f"❌ Scraper critical failure: {exc}")

    return all_reviews
