# filename: app/services/scraper.py
import os
import logging
import asyncio
import re
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

from serpapi import GoogleSearch
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Company, Review

logger = logging.getLogger("app.scraper")

# API Keys
# Primary Key
SERPAPI_KEY = "f9f41e452ea716ca1e760081b94763a404c9e1e07aef30def9c6a05391890e8d"
# Verified Key from your Serper Dashboard screenshot
SERPER_API_KEY = "d978f3563ac6dd6bcce594ac487142f614c8db08"

def parse_relative_date(date_text: str) -> datetime:
    if not date_text or not isinstance(date_text, str):
        return datetime.utcnow()
    now = datetime.utcnow()
    match = re.search(r'(\d+)', date_text)
    quantity = int(match.group(1)) if match else 1
    date_text = date_text.lower()
    if 'second' in date_text: return now - timedelta(seconds=quantity)
    elif 'minute' in date_text: return now - timedelta(minutes=quantity)
    elif 'hour' in date_text: return now - timedelta(hours=quantity)
    elif 'day' in date_text: return now - timedelta(days=quantity)
    elif 'week' in date_text: return now - timedelta(weeks=quantity)
    elif 'month' in date_text: return now - timedelta(days=quantity * 30)
    elif 'year' in date_text: return now - timedelta(days=quantity * 365)
    return now

async def fetch_from_serper_fallback(company_name: str, limit: int) -> List[Dict[str, Any]]:
    """
    Final optimized fallback using your specific Serper Key.
    Uses the /places endpoint which is more structured for business reviews.
    """
    logger.info(f"📡 Serper Fallback engaged for: {company_name}")
    
    if not SERPER_API_KEY:
        logger.error("❌ SERPER_API_KEY is missing from configuration.")
        return []

    url = "https://google.serper.dev/places"
    payload = {
        "q": f"{company_name} reviews",
        "gl": "pk",
        "hl": "en"
    }
    headers = {
        'X-API-KEY': SERPER_API_KEY,
        'Content-Type': 'application/json'
    }
    
    try:
        response = await asyncio.to_thread(lambda: requests.post(url, headers=headers, json=payload, timeout=15))
        response.raise_for_status()
        data = response.json()
        
        places = data.get("places", [])
        results = []
        
        if places:
            # Extract reviews from the most relevant place found
            raw_reviews = places[0].get("reviews", [])
            for r in raw_reviews:
                if len(results) >= limit: break
                    
                results.append({
                    "google_review_id": f"serper_{datetime.utcnow().timestamp()}_{len(results)}",
                    "author_name": r.get("user", "Anonymous"),
                    "rating": int(r.get("rating", 5)),
                    "text": r.get("snippet") or r.get("text") or "No content",
                    "google_review_time": datetime.utcnow(),
                    "review_likes": 0
                })
        
        logger.info(f"✅ Serper successfully scraped {len(results)} reviews.")
        return results
    except Exception as e:
        logger.error(f"❌ Serper API total failure: {e}")
        return []

async def fetch_reviews_from_google(
    place_id: Optional[str] = None,
    company_id: Optional[int] = None,
    session: Optional[AsyncSession] = None,
    target_limit: int = 100,
    **kwargs
) -> List[Dict[str, Any]]:
    all_reviews: List[Dict[str, Any]] = []
    existing_ids = set()
    company_name = "Business"

    try:
        # 1. Setup Context & Check for Existing Data
        if session and company_id:
            # Fetch all existing IDs once to prevent duplicates
            stmt = select(Review.google_review_id).where(Review.company_id == company_id)
            res = await session.execute(stmt)
            existing_ids = set(res.scalars().all())
            
            # Identify company name for fallback search
            comp_stmt = select(Company).where(Company.id == company_id)
            comp_res = await session.execute(comp_stmt)
            company = comp_res.scalars().first()
            if company:
                company_name = company.name
                place_id = place_id or company.google_place_id

        if not place_id:
            logger.error("❌ Critical: No Place ID provided.")
            return []

        # 2. Execute SerpApi Sync
        logger.info(f"🚀 Syncing {company_name} (Place ID: {place_id})")
        
        next_page_token = None
        while len(all_reviews) < target_limit:
            params = {
                "engine": "google_maps_reviews",
                "place_id": place_id,
                "api_key": SERPAPI_KEY,
                "next_page_token": next_page_token,
                "sort_by": "newest"
            }
            
            # Run blocking API call in a thread to keep FastAPI responsive
            results = await asyncio.to_thread(lambda: GoogleSearch(params).get_dict())
            
            if "error" in results:
                raise Exception(results["error"])

            reviews = results.get("reviews", [])
            if not reviews: break

            for r in reviews:
                r_id = r.get("review_id")
                
                # CRITICAL FIX: Stop if we hit a review we already have.
                # Since results are sorted by "newest", hitting an old ID means 
                # we have synced everything new.
                if r_id in existing_ids:
                    logger.info(f"📍 Sync caught up for {company_name}. No more new reviews.")
                    return all_reviews
                
                if len(all_reviews) >= target_limit: break
                
                all_reviews.append({
                    "google_review_id": r_id,
                    "author_name": r.get("user", {}).get("name"),
                    "rating": int(r.get("rating", 5)),
                    "text": r.get("text") or r.get("snippet") or "No content",
                    "google_review_time": parse_relative_date(r.get("date", "")),
                    "review_likes": r.get("likes", 0)
                })
            
            # Handle Pagination
            next_page_token = results.get("serpapi_pagination", {}).get("next_page_token")
            if not next_page_token: break
            
        return all_reviews

    except Exception as primary_err:
        logger.warning(f"⚠️ Primary API failed: {primary_err}. Falling back to Serper.dev...")
        return await fetch_from_serper_fallback(company_name, target_limit)

    except Exception as exc:
        logger.error(f"❌ Scraper failure: {exc}")
        return []
