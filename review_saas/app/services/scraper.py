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
SERPAPI_KEY = "f9f41e452ea716ca1e760081b94763a404c9e1e07aef30def9c6a05391890e8d".strip()
SERPER_API_KEY = os.getenv("SERPER_API_KEY") 

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

async def fetch_from_serper_fallback(place_id: str, limit: int, skip_count: int) -> List[Dict[str, Any]]:
    """
    Dedicated Fallback using Serper.dev REVIEWS endpoint.
    This endpoint allows for deep pagination to find older reviews.
    """
    logger.info(f"📡 Deep Fallback: Scanning Serper Reviews for Place ID: {place_id} (Skip: {skip_count})")
    
    if not SERPER_API_KEY:
        logger.error("❌ SERPER_API_KEY missing in Railway Variables.")
        return []

    url = "https://google.serper.dev/reviews"
    
    # Calculate the page: Serper shows 10 reviews per page.
    # If we have 200 in DB, we need to start at Page 21.
    target_page = (skip_count // 10) + 1
    
    payload = {
        "place_id": place_id,
        "page": target_page
    }
    headers = {
        'X-API-KEY': SERPER_API_KEY,
        'Content-Type': 'application/json'
    }
    
    try:
        response = await asyncio.to_thread(lambda: requests.post(url, headers=headers, json=payload))
        response.raise_for_status()
        data = response.json()
        
        # The 'reviews' endpoint returns a direct list of reviews
        raw_reviews = data.get("reviews", [])
        results = []
        
        for r in raw_reviews:
            if len(results) >= limit:
                break

            results.append({
                "google_review_id": r.get("reviewId") or f"serper_{datetime.utcnow().timestamp()}",
                "author_name": r.get("user", {}).get("name") or "Anonymous",
                "rating": int(r.get("rating", 5)),
                "text": r.get("snippet") or r.get("text") or "No content",
                "google_review_time": datetime.utcnow(), # Placeholder for fallback
                "review_likes": 0
            })
        
        logger.info(f"✅ Serper.dev Reviews engine collected {len(results)} reviews.")
        return results
    except Exception as e:
        logger.error(f"❌ Serper Reviews Endpoint Failed: {e}")
        return []

async def fetch_reviews_from_google(
    place_id: Optional[str] = None,
    company_id: Optional[int] = None,
    session: Optional[AsyncSession] = None,
    target_limit: int = 100,
    days_back: int = 3650, 
    **kwargs
) -> List[Dict[str, Any]]:
    all_reviews: List[Dict[str, Any]] = []

    try:
        current_db_count = 0
        if session and company_id:
            count_res = await session.execute(select(func.count(Review.id)).where(Review.company_id == company_id))
            current_db_count = count_res.scalar() or 0
            
            if not place_id:
                comp_res = await session.execute(select(Company).where(Company.id == company_id))
                company = comp_res.scalars().first()
                place_id = company.google_place_id if company else None

        if not place_id:
            return []

        cutoff_date = datetime.utcnow() - timedelta(days=days_back)
        logger.info(f"🚀 Syncing: DB has {current_db_count}. Fetching NEXT {target_limit} reviews.")
        
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

                results = await asyncio.to_thread(lambda: GoogleSearch(params).get_dict())
                if "error" in results:
                    raise Exception(results["error"])

                reviews = results.get("reviews", [])
                if not reviews:
                    break

                for r in reviews:
                    total_seen_on_google += 1
                    if total_seen_on_google <= current_db_count:
                        continue

                    if len(all_reviews) >= target_limit:
                        break
                    
                    p_date = parse_relative_date(r.get("date", ""))
                    if p_date < cutoff_date:
                        return all_reviews

                    all_reviews.append({
                        "google_review_id": r.get("review_id"),
                        "author_name": r.get("user", {}).get("name"),
                        "rating": int(r.get("rating", 5)),
                        "text": r.get("text") or r.get("snippet") or "No content",
                        "google_review_time": p_date,
                        "review_likes": r.get("likes", 0)
                    })

                next_page_token = results.get("serpapi_pagination", {}).get("next_page_token")
                if not next_page_token:
                    break
            
            return all_reviews

        except Exception as primary_err:
            logger.warning(f"⚠️ SerpApi Error: {primary_err}. Switching to Fallback...")
            # CALLING THE NEW DEEP REVIEWS FALLBACK
            return await fetch_from_serper_fallback(place_id, target_limit, current_db_count)

    except Exception as exc:
        logger.error(f"❌ Scraper failure: {exc}")
        return []
