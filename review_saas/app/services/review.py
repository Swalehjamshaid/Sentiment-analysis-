# filename: app/services/review.py

from __future__ import annotations
import logging
import asyncio
from typing import Any, Dict, List, Optional, Set
from datetime import datetime

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, insert

from app.core.config import settings
from app.core.models import Review

# Localized signal registry to allow manual stops from the UI
cancel_requests: Set[int] = set()

logger = logging.getLogger(__name__)

class OutscraperReviewsClient:
    """
    Client for interacting with Outscraper Google Maps Reviews API.
    """
    def __init__(self, *, base_url: Optional[str] = None, api_key: Optional[str] = None) -> None:
        self.base_url = (base_url or settings.OUTSCRAPER_BASE_URL).rstrip("/")
        self.api_key = (api_key or settings.OUTSCRAPER_API_KEY).strip()
        self.reviews_endpoint = f"{self.base_url}/maps/reviews-v3"

    async def fetch_batch(self, client: httpx.AsyncClient, query: str, limit: int, skip: int) -> List[Dict[str, Any]]:
        """
        Fetches a specific batch of reviews using the skip (offset) parameter.
        """
        params = {
            "query": query,
            "reviewsLimit": limit,
            "skip": skip,
            "async": "false",
            "ignoreEmpty": "true"
        }
        headers = {"X-API-KEY": self.api_key}
        try:
            # Long read timeout for deep scraping sessions
            response = await client.get(self.reviews_endpoint, params=params, headers=headers)
            response.raise_for_status()
            data = response.json().get("data", [])
            return data[0].get("reviews_data", []) if data else []
        except Exception as e:
            logger.error(f"Batch fail at skip {skip}: {str(e)}")
            return []

async def ingest_outscraper_reviews(company_obj: Any, session: AsyncSession, max_reviews: int = 1000) -> int:
    """
    HIGH-SPEED CHRONOLOGICAL INGESTION:
    1. Determines current DB count to set the starting 'skip' value.
    2. Fetches from the most recent available review down to previous ones.
    3. Uses Producer-Consumer pattern for maximum throughput.
    """
    client_wrapper = OutscraperReviewsClient()
    query = getattr(company_obj, "google_place_id", None) or getattr(company_obj, "name", None)

    if not query:
        logger.error(f"No identifier found for company: {company_obj.name}")
        return 0

    # 1. Load existing IDs to prevent any overlapping duplicates
    stmt = select(Review.google_review_id).where(Review.company_id == company_obj.id)
    result = await session.execute(stmt)
    existing_ids = set(result.scalars().all())
    
    # 2. Set the starting point based on current database size
    # This ensures Batch 2 starts exactly where Batch 1 ended.
    current_db_count = len(existing_ids)
    
    batch_size = 250
    queue: asyncio.Queue = asyncio.Queue(maxsize=50)
    total_new = 0
    
    # Limit parallel connections to avoid API rate limits
    fetch_sem = asyncio.Semaphore(5)

    async def fetch_worker(client: httpx.AsyncClient, skip: int):
        """Producer: Fetches a block of 250 reviews from the historical offset"""
        if company_obj.id in cancel_requests:
            return

        async with fetch_sem:
            batch = await client_wrapper.fetch_batch(client, query, batch_size, skip)
            if batch:
                await queue.put(batch)

    async def producer():
        """Coordinator: Calculates the skip range and triggers workers"""
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(10.0, read=300.0),
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5)
        ) as client:
            tasks = []
            # Start from current_db_count and move backwards by 'batch_size'
            for skip in range(current_db_count, current_db_count + max_reviews, batch_size):
                if company_obj.id in cancel_requests:
                    logger.info(f"Stop signal received for {company_obj.name}")
                    break
                
                tasks.append(asyncio.create_task(fetch_worker(client, skip)))
            
            await asyncio.gather(*tasks)

        # Signal consumer that all batches are fetched
        await queue.put(None)

    async def consumer():
        """Consumer: Validates and performs bulk database inserts"""
        nonlocal total_new
        while True:
            batch = await queue.get()
            if batch is None:
                queue.task_done()
                break

            to_insert = []
            for raw in batch:
                rid = raw.get("review_id")
                # Strict check: skip if ID is missing or already in our DB
                if not rid or rid in existing_ids:
                    continue

                dt_obj = None
                raw_ts = raw.get("review_datetime_utc")
                if raw_ts:
                    try:
                        dt_obj = datetime.strptime(raw_ts, "%m/%d/%Y %H:%M:%S")
                    except Exception: 
                        pass

                to_insert.append({
                    "company_id": company_obj.id,
                    "google_review_id": rid,
                    "author_name": raw.get("author_title"),
                    "rating": raw.get("review_rating"),
                    "text": raw.get("review_text"),
                    "google_review_time": dt_obj,
                    "source_platform": "Google"
                })
                # Prevent duplicates within the same ingestion run
                existing_ids.add(rid)

            if to_insert:
                # Bulk insert for speed
                await session.execute(insert(Review), to_insert)
                await session.commit()
                total_new += len(to_insert)
            
            queue.task_done()

    # Run producer and consumer in parallel
    await asyncio.gather(producer(), asyncio.create_task(consumer()))

    # Clear kill-switch
    if company_obj.id in cancel_requests:
        cancel_requests.remove(company_obj.id)

    logger.info(f"✅ Ingested {total_new} new historical reviews for {company_obj.name}")
    return total_new
