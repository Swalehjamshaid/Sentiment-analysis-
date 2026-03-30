import os
import logging
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import re

from serpapi import GoogleSearch
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Company, Review

logger = logging.getLogger("app.scraper")

# Verified API Key
SERPAPI_KEY = "f9f41e452ea716ca1e760081b94763a404c9e1e07aef30def9c6a05391890e8d".strip()

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
        # 1. Check current count in DB
        current_db_count = 0
        if session and company_id:
            # We count how many reviews we already have for THIS specific company
            count_stmt = select(func.count(Review.id)).where(Review.company_id == company_id)
            count_res = await session.execute(count_stmt)
            current_db_count = count_res.scalar() or 0

        target_place_id = place_id
        if not target_place_id and company_id and session:
            result = await session.execute(select(Company).where(Company.id == company_id))
            company = result.scalar_one_or_none()
            target_place_id = company.google_place_id if company else None

        if not target_place_id:
            return []

        cutoff_date = datetime.utcnow() - timedelta(days=days_back)
        
        # LOGIC: If we have 100 reviews, we skip 100. If we have 200, we skip 200.
        logger.info(f"🚀 Deep Sync: DB already has {current_db_count}. Fetching NEXT {target_limit} older reviews.")
        
        next_page_token: Optional[str] = None
        total_seen_on_google = 0

        while len(all_reviews) < target_limit:
            params = {
                "engine": "google_maps_reviews",
                "place_id": target_place_id,
                "api_key": SERPAPI_KEY,
                "next_page_token": next_page_token,
                "sort_by": "newest"
            }

            results = await asyncio.to_thread(lambda: GoogleSearch(params).get_dict())
            
            if "error" in results:
                logger.error(f"❌ SerpApi Error: {results['error']}")
                break

            reviews = results.get("reviews", [])
            if not reviews:
                break

            for r in reviews:
                total_seen_on_google += 1
                
                # --- THE SKIP ATTRIBUTE ---
                # We skip everything we already have in our database
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

        logger.info(f"✅ Collected {len(all_reviews)} BRAND NEW older reviews.")

    except Exception as exc:
        logger.error(f"❌ Scraper failure: {exc}")

    return all_reviews
