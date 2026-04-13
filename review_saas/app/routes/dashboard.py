# filename: app/services/scraper.py
# ==========================================================
# REVIEW INTELLIGENCE SCRAPER — DEDUPLICATION & SYNC ALIGNED
# ==========================================================

import os
import logging
import asyncio
import re
import json
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

# Official SerpApi Wrapper
from serpapi import GoogleSearch
# Database dependencies
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Internal models
from app.core.models import Company, Review

logger = logging.getLogger("app.scraper")

# ==========================================================
# API CONFIGURATION
# ==========================================================
SERPAPI_KEY = "f9f41e452ea716ca1e760081b94763a404c9e1e07aef30def9c6a05391890e8d"
SERPER_API_KEY = "d978f3563ac6dd6bcce594ac487142f614c8db08"

# ==========================================================
# UTILITY FUNCTIONS
# ==========================================================
def parse_relative_date(date_text: str) -> datetime:
    """ Converts relative time strings to UTC datetime objects. """
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

# ==========================================================
# SERPER.DEV FALLBACK
# ==========================================================
async def fetch_from_serper_fallback(company_name: str, limit: int = 10) -> List[Dict[str, Any]]:
    """ Fallback using Serper.dev for web mentions. """
    url = "https://google.serper.dev/search"
    payload = json.dumps({"q": f"{company_name} reviews", "gl": "pk", "hl": "en"})
    headers = {'X-API-KEY': SERPER_API_KEY, 'Content-Type': 'application/json'}
    
    try:
        response = await asyncio.to_thread(lambda: requests.post(url, headers=headers, data=payload, timeout=15))
        data = response.json()
        results = []
        for idx, entry in enumerate(data.get("organic", [])):
            if len(results) >= limit: break
            results.append({
                "google_review_id": f"serper_{int(datetime.utcnow().timestamp())}_{idx}",
                "author_name": entry.get("title", "Web Mention"),
                "rating": 5, 
                "text": entry.get("snippet", "No content"),
                "google_review_time": datetime.utcnow(),
                "review_likes": 0
            })
        return results
    except Exception as e:
        logger.error(f"Serper Fallback Error: {e}")
        return []

# ==========================================================
# MAIN SCRAPER LOGIC (WITH DEDUPLICATION)
# ==========================================================
async def fetch_reviews_from_google(
    place_id: Optional[str] = None,
    company_id: Optional[int] = None,
    session: Optional[AsyncSession] = None,
    target_limit: int = 100,
    **kwargs
) -> List[Dict[str, Any]]:
    """
    Fetches reviews and implements a hard-stop if a duplicate ID is found.
    """
    all_reviews: List[Dict[str, Any]] = []
    existing_ids = set()
    company_name = "Business"

    try:
        # 1. Load context and existing IDs to prevent duplicates
        if session and company_id:
            stmt = select(Review.google_review_id).where(Review.company_id == company_id)
            res = await session.execute(stmt)
            existing_ids = set(res.scalars().all())
            
            comp_stmt = select(Company).where(Company.id == company_id)
            comp_res = await session.execute(comp_stmt)
            company = comp_res.scalars().first()
            if company:
                company_name = company.name
                place_id = place_id or company.google_place_id

        if not place_id:
            logger.error("❌ Aborting: No Place ID provided.")
            return []

        # 2. SerpApi Sync Loop
        logger.info(f"🚀 Syncing {company_name} | Filtering duplicates...")
        
        next_page_token = None
        while len(all_reviews) < target_limit:
            params = {
                "engine": "google_maps_reviews",
                "place_id": place_id,
                "api_key": SERPAPI_KEY,
                "next_page_token": next_page_token,
                "sort_by": "newest" # Ensure we process the latest first
            }
            
            search = await asyncio.to_thread(lambda: GoogleSearch(params).get_dict())
            if "error" in search: raise Exception(search["error"])

            reviews = search.get("reviews", [])
            if not reviews: break

            for r in reviews:
                r_id = r.get("review_id")
                
                # DUPLICATE PROTECTION: Hard stop if ID is in database
                if r_id in existing_ids:
                    logger.info(f"📍 Database caught up for {company_name}. No new reviews found.")
                    return all_reviews
                
                # Local uniqueness check
                if any(ar['google_review_id'] == r_id for ar in all_reviews): continue

                if len(all_reviews) >= target_limit: break
                
                all_reviews.append({
                    "google_review_id": r_id,
                    "author_name": r.get("user", {}).get("name", "Anonymous"),
                    "rating": int(r.get("rating", 5)),
                    "text": r.get("text") or r.get("snippet") or "No content.",
                    "google_review_time": parse_relative_date(r.get("date", "")),
                    "review_likes": r.get("likes", 0)
                })
            
            next_page_token = search.get("serpapi_pagination", {}).get("next_page_token")
            if not next_page_token: break
            
        return all_reviews

    except Exception as primary_err:
        logger.warning(f"⚠️ SerpApi Path interrupted. Switching to Serper Fallback...")
        return await fetch_from_serper_fallback(company_name, target_limit)
