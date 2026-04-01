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
SERPAPI_KEY = "f9f41e452ea716ca1e760081b94763a404c9e1e07aef30def9c6a05391890e8d".strip()
# Secondary Key (From Railway Environment Variables)
SERPER_API_KEY = os.getenv("SERPER_API_KEY") 

def parse_relative_date(date_text: str) -> datetime:
    """Converts Google's relative strings like '3 months ago' into datetime objects"""
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

async def fetch_from_serper_fallback(company_name: str, limit: int, skip_count: int) -> List[Dict[str, Any]]:
    """
    Robust Fallback logic for Serper.dev.
    Uses business name search to find reviews when SerpApi fails.
    """
    logger.info(f"📡 Fallback Triggered: Serper.dev searching for '{company_name}' (Skip: {skip_count})")
    
    if not SERPER_API_KEY:
        logger.error("❌ SERPER_API_KEY is missing in Railway Variables.")
        return []

    url = "https://google.serper.dev/search"
    
    # We use a natural search query which is more successful on Serper
    payload = {
        "q": f"{company_name} reviews",
        "gl": "pk", # Focused on Pakistan
        "hl": "en",
        "type": "places",
        "page": (skip_count // 10) + 1 # Converts skip count to page numbers
    }
    
    headers = {
        'X-API-KEY': SERPER_API_KEY,
        'Content-Type': 'application/json'
    }
    
    try:
        response = await asyncio.to_thread(lambda: requests.post(url, headers=headers, json=payload))
        response.raise_for_status()
        data = response.json()
        
        places = data.get("places", [])
        results = []
        
        if places:
            # Get reviews from the top matched place
            raw_reviews = places[0].get("reviews", [])
            for r in raw_reviews:
                if len(results) >= limit:
                    break
                
                results.append({
                    "google_review_id": f"serper_{datetime.utcnow().timestamp()}_{len(results)}",
                    "author_name": r.get("user", "Anonymous"),
                    "rating": int(r.get("rating", 5)),
                    "text": r.get("snippet") or r.get("text") or "No content",
                    "google_review_time": datetime.utcnow(), # Serper snippets don't always give exact dates
                    "review_likes": 0
                })
        
        logger.info(f"✅ Serper.dev fallback successfully collected {len(results)} reviews.")
        return results

    except Exception as e:
        logger.error(f"❌ Serper.dev Fallback Failed: {e}")
        return []

async def fetch_reviews_from_google(
    place_id: Optional[str] = None,
    company_id: Optional[int] = None,
    session: Optional[AsyncSession] = None,
    target_limit: int = 100,
    days_back: int = 3650, 
    **kwargs
) -> List[Dict[str, Any]]:
    """
    Main entry point for fetching reviews.
    Tries SerpApi first, then falls back to Serper.dev.
    """
    all_reviews: List[Dict[str, Any]] = []

    try:
        # 1. Check current count in DB for the Skip/Offset Logic
        current_db_count = 0
        company_name = "Business"
        
        if session and company_id:
            # Count existing reviews
            count_stmt = select(func.count(Review.id)).where(Review.company_id == company_id)
            count_res = await session.execute(count_stmt)
            current_db_count = count_res.scalar() or 0
            
            # Get company name for fallback accuracy
            comp_stmt = select(Company).where(Company.id == company_id)
            comp_res = await session.execute(comp_stmt)
            company = comp_res.scalars().first()
            if company:
                company_name = company.name
                if not place_id:
                    place_id = company.google_place_id

        if not place_id:
            logger.error("❌ No Place ID or Company Name found to start search.")
            return []

        cutoff_date = datetime.utcnow() - timedelta(days=days_back)
        logger.info(f"🚀 Deep Sync: DB has {current_db_count}. Fetching NEXT {target_limit} older reviews.")
        
        # 2. PRIMARY ATTEMPT: SerpApi
        next_page_token: Optional[str] = None
        total_seen_on_google = 0

        try:
            while len(all_reviews) < target_limit:
                params = {
                    "engine": "google_maps_reviews",
                    "place_id": place_id,
                    "api_key": SERPAPI_KEY,
                    "next_page_token": next_page_token,
                    "sort_by": "newest"
                }

                # Use to_thread to prevent blocking the async loop
                results = await asyncio.to_thread(lambda: GoogleSearch(params).get_dict())
                
                if "error" in results:
                    raise Exception(results["error"])

                reviews = results.get("reviews", [])
                if not reviews:
                    break

                for r in reviews:
                    total_seen_on_google += 1
                    
                    # THE SKIP ATTRIBUTE
                    if total_seen_on_google <= current_db_count:
                        continue

                    if len(all_reviews) >= target_limit:
                        break
                    
                    parsed_date = parse_relative_date(r.get("date", ""))
                    if parsed_date < cutoff_date:
                        return all_reviews

                    all_reviews.append({
                        "google_review_id": r.get("review_id"),
                        "author_name": r.get("user", {}).get("name"),
                        "rating": int(r.get("rating", 5)),
                        "text": r.get("text") or r.get("snippet") or "No content",
                        "google_review_time": parsed_date,
                        "review_likes": r.get("likes", 0)
                    })

                next_page_token = results.get("serpapi_pagination", {}).get("next_page_token")
                if not next_page_token:
                    break
            
            return all_reviews

        except Exception as primary_err:
            # 3. FALLBACK ATTEMPT: Serper.dev
            logger.warning(f"⚠️ SerpApi failed: {primary_err}. Switching to Fallback...")
            return await fetch_from_serper_fallback(company_name, target_limit, current_db_count)

    except Exception as exc:
        logger.error(f"❌ Critical Scraper failure: {exc}")
        return []
